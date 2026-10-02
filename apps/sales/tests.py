from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.customers.models import Customer
from apps.products.models import Brand, Category, Product, ProductUnit, Unit
from apps.stock.models import Stock
from apps.stock.services import format_stock_quantity
from .models import Sale, SaleItem


class SaleAvailabilityTests(TestCase):
    """Chupa ya Soda base unit, Crate ya Soda = 24 chupa.

    Stock is always stored in whole base units; everything shown to the user is
    derived from that single number.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email="seller@example.com",
            phone="255700000010",
            password="safe-password-123",
            role=User.Roles.SALESPERSON,
        )
        self.customer = Customer.objects.create(name="Plate Buyer", created_by=self.user)
        category = Category.objects.create(name="Beverages", created_by=self.user)
        self.brand = Brand.objects.create(
            name="Mirinda", category=category, created_by=self.user
        )
        self.chupa = Unit.objects.create(
            name="Chupa ya Soda", abbreviation="CHP", created_by=self.user
        )
        self.crate = Unit.objects.create(
            name="Crate ya Soda", abbreviation="CS", created_by=self.user
        )
        self.product = Product.objects.create(
            brand=self.brand,
            base_unit=self.chupa,
            name="Mirinda Orange",
            buying_price=Decimal("800.00"),
            selling_price=Decimal("1000.00"),
            created_by=self.user,
        )
        self.chupa_config = ProductUnit.objects.create(
            product=self.product,
            unit=self.chupa,
            conversion_factor=1,
            buying_price=Decimal("800.00"),
            selling_price=Decimal("1000.00"),
            created_by=self.user,
        )
        self.crate_config = ProductUnit.objects.create(
            product=self.product,
            unit=self.crate,
            conversion_factor=24,
            buying_price=Decimal("18000.00"),
            selling_price=Decimal("22000.00"),
            created_by=self.user,
        )
        self.stock = Stock.objects.create(
            product=self.product, quantity=240, created_by=self.user
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def set_stock(self, quantity):
        Stock.objects.filter(product=self.product).update(quantity=quantity)
        self.stock.refresh_from_db()
        return self.stock

    def post_sale(self, quantity, product_unit=None, unit_price="22000.00"):
        return self.client.post(
            "/api/sales/",
            {
                "customer": str(self.customer.uuid),
                "sale_date": timezone.now().isoformat(),
                "items": [
                    {
                        "product": str(self.product.uuid),
                        "product_unit": str((product_unit or self.crate_config).uuid),
                        "quantity": quantity,
                        "unit_price": unit_price,
                    }
                ],
            },
            format="json",
        )

    def stock_quantity(self):
        return Stock.objects.get(product=self.product).quantity

    def availability(self, product_unit):
        response = self.client.get(
            f"/api/stocks/availability/?product={self.product.uuid}&unit={product_unit.uuid}"
        )
        self.assertEqual(response.status_code, 200, response.data)
        return response.data[0]

    # ------------------------------------------------------------------
    # Spec cases 1-5: availability is expressed in the selected unit
    # ------------------------------------------------------------------

    def test_case_1_stock_240_bottles_sold_as_bottles(self):
        self.set_stock(240)

        data = self.availability(self.chupa_config)

        self.assertEqual(data["base_stock"], 240)
        self.assertEqual(data["base_unit"], "Chupa ya Soda")
        self.assertEqual(data["selected_unit"], "Chupa ya Soda")
        self.assertEqual(data["conversion_factor"], 1)
        self.assertEqual(data["available_quantity"], 240)
        self.assertEqual(data["remainder_base_quantity"], 0)
        self.assertEqual(data["available_display"], "240 CHP")

    def test_case_2_stock_240_bottles_sold_as_crates(self):
        self.set_stock(240)

        data = self.availability(self.crate_config)

        self.assertEqual(data["available_quantity"], 10)
        self.assertEqual(data["remainder_base_quantity"], 0)
        self.assertEqual(data["available_display"], "10 CS")

    def test_case_3_stock_239_bottles_sold_as_crates(self):
        self.set_stock(239)

        data = self.availability(self.crate_config)

        self.assertEqual(data["available_quantity"], 9)
        self.assertEqual(data["remainder_base_quantity"], 23)
        self.assertEqual(data["available_display"], "9 CS + 23 CHP")

    def test_case_4_stock_50_bottles_sold_as_crates(self):
        self.set_stock(50)

        data = self.availability(self.crate_config)

        self.assertEqual(data["available_quantity"], 2)
        self.assertEqual(data["remainder_base_quantity"], 2)
        self.assertEqual(data["available_display"], "2 CS + 2 CHP")

    def test_case_5_no_partial_crate_can_be_sold(self):
        self.set_stock(23)

        data = self.availability(self.crate_config)

        self.assertEqual(data["available_quantity"], 0)
        self.assertEqual(data["remainder_base_quantity"], 23)
        self.assertEqual(data["available_display"], "0 CS + 23 CHP")

        response = self.post_sale(1, self.crate_config)

        self.assertEqual(response.status_code, 400)
        self.assertIn("Insufficient stock", str(response.data))
        self.assertEqual(self.stock_quantity(), 23)

        # The same stock is sellable one bottle at a time.
        response = self.post_sale(
            23, self.chupa_config, unit_price="1000.00"
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(self.stock_quantity(), 0)

    def test_availability_endpoint_returns_every_configured_unit(self):
        self.set_stock(239)

        response = self.client.get(f"/api/stocks/availability/?product={self.product.uuid}")
        self.assertEqual(response.status_code, 200, response.data)

        by_unit = {entry["selected_unit"]: entry for entry in response.data}
        self.assertEqual(set(by_unit), {"Chupa ya Soda", "Crate ya Soda"})
        self.assertEqual(by_unit["Chupa ya Soda"]["available_display"], "239 CHP")
        self.assertEqual(by_unit["Crate ya Soda"]["available_display"], "9 CS + 23 CHP")

    def test_availability_rejects_a_unit_of_another_product(self):
        other = Product.objects.create(
            brand=self.brand,
            base_unit=self.chupa,
            name="Water",
            buying_price=Decimal("300.00"),
            selling_price=Decimal("500.00"),
            created_by=self.user,
        )
        foreign = ProductUnit.objects.create(
            product=other,
            unit=self.crate,
            conversion_factor=20,
            buying_price=Decimal("6000.00"),
            selling_price=Decimal("8000.00"),
            created_by=self.user,
        )

        response = self.client.get(
            f"/api/stocks/availability/?product={self.product.uuid}&unit={foreign.uuid}"
        )

        self.assertEqual(response.status_code, 400)

    # ------------------------------------------------------------------
    # Spec cases 6-8: whole-unit conversion and validation
    # ------------------------------------------------------------------

    def test_stock_lookup_by_product_uuid_matches_the_stock_api(self):
        """Regression: stock rows must be findable by product uuid.

        The sale form looks up `stockRows.find(row => row.product === uuid)`.
        When the API returned the numeric row id instead, every product looked
        out of stock even though it had stock.
        """
        self.set_stock(50)

        stock_row = self.client.get("/api/stocks/").data["results"][0]
        self.assertEqual(str(stock_row["product"]), str(self.product.uuid))

        # Same lookup the form performs, and the availability the form derives.
        availability = self.availability(self.crate_config)
        self.assertEqual(availability["available_quantity"], 2)
        self.assertEqual(availability["available_display"], "2 CS + 2 CHP")

        # And the sale the form would submit is accepted by the backend.
        response = self.post_sale(2, self.crate_config)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(self.stock_quantity(), 2)

    def test_case_6_selling_nine_crates_leaves_the_remainder(self):
        self.set_stock(239)

        response = self.post_sale(9, self.crate_config)

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(self.stock_quantity(), 23)

        item = SaleItem.objects.get()
        self.assertEqual(item.quantity, 9)
        self.assertEqual(item.conversion_factor_used, 24)
        self.assertEqual(item.base_quantity, 216)

    def test_case_7_ten_crates_are_rejected_and_stock_is_untouched(self):
        self.set_stock(239)

        response = self.post_sale(10, self.crate_config)

        self.assertEqual(response.status_code, 400)
        message = str(response.data)
        self.assertIn("Insufficient stock", message)
        self.assertIn("239 CHP", message)
        self.assertIn("9 CS + 23 CHP", message)
        self.assertIn("10 CS", message)
        self.assertIn("240 Chupa ya Soda", message)
        self.assertEqual(self.stock_quantity(), 239)

    def test_case_8_fractional_quantities_are_rejected_everywhere(self):
        for quantity in ["1.5", 1.5, "0.5"]:
            with self.subTest(quantity=quantity):
                response = self.post_sale(quantity, self.crate_config)
                self.assertEqual(response.status_code, 400)
                self.assertIn("whole number", str(response.data))

        for quantity in [0, -2]:
            with self.subTest(quantity=quantity):
                response = self.post_sale(quantity, self.crate_config)
                self.assertEqual(response.status_code, 400)

        self.assertEqual(self.stock_quantity(), 240)
        self.assertEqual(SaleItem.objects.count(), 0)

    def test_zero_quantity_is_rejected(self):
        response = self.post_sale(0, self.crate_config)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.stock_quantity(), 240)

    def test_unit_belonging_to_another_product_is_rejected(self):
        other = Product.objects.create(
            brand=self.brand,
            base_unit=self.chupa,
            name="Water",
            buying_price=Decimal("300.00"),
            selling_price=Decimal("500.00"),
            created_by=self.user,
        )
        foreign = ProductUnit.objects.create(
            product=other,
            unit=self.crate,
            conversion_factor=20,
            buying_price=Decimal("6000.00"),
            selling_price=Decimal("8000.00"),
            created_by=self.user,
        )

        response = self.post_sale(1, foreign)

        self.assertEqual(response.status_code, 400)
        self.assertIn("not configured for this product", str(response.data))

    def test_inactive_product_cannot_be_sold(self):
        Product.objects.filter(pk=self.product.pk).update(is_active=False)

        response = self.post_sale(1, self.crate_config)

        self.assertEqual(response.status_code, 400)
        self.assertIn("not an active product", str(response.data))

    # ------------------------------------------------------------------
    # Sale mechanics
    # ------------------------------------------------------------------

    def test_posted_sale_type_is_ignored_and_defaults_to_retail(self):
        response = self.post_sale(1, self.chupa_config, "1000.00")

        self.assertEqual(response.status_code, 201, response.data)
        item = SaleItem.objects.get()
        self.assertEqual(item.sale_type, "retail")
        self.assertEqual(response.data["items"][0]["sale_type"], "retail")

    def test_selling_a_single_chupa_leaves_the_rest_as_chupas(self):
        response = self.post_sale(
            1, self.chupa_config, unit_price="1000.00"
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(self.stock_quantity(), 239)

        item = SaleItem.objects.get()
        self.assertEqual(item.quantity, 1)
        self.assertEqual(item.base_quantity, 1)
        self.assertEqual(item.conversion_factor_used, 1)

        self.assertEqual(format_stock_quantity(self.product, 239), "9 CS + 23 CHP")

    def test_selling_two_crates_removes_forty_eight_chupas(self):
        response = self.post_sale(2, self.crate_config)

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(self.stock_quantity(), 192)

        item = SaleItem.objects.get()
        self.assertEqual(item.base_quantity, 48)
        self.assertEqual(item.conversion_factor_used, 24)
        self.assertEqual(item.subtotal, Decimal("44000.00"))
        self.assertEqual(format_stock_quantity(self.product, 192), "8 CS")

    def test_stock_never_goes_negative_across_many_transactions(self):
        self.assertEqual(self.post_sale(2, self.crate_config).status_code, 201)
        self.assertEqual(
            self.post_sale(5, self.chupa_config, "1000.00").status_code, 201
        )
        self.assertEqual(self.stock_quantity(), 187)

        response = self.post_sale(10, self.crate_config)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.stock_quantity(), 187)

    def test_movement_records_transaction_and_base_units(self):
        self.post_sale(2, self.crate_config)

        movement = self.client.get("/api/stock-movements/").data["results"][0]
        self.assertEqual(movement["movement_type"], "Sales")
        self.assertEqual(movement["transaction_quantity"], 2)
        self.assertEqual(movement["transaction_unit_name"], "Crate ya Soda")
        self.assertEqual(movement["base_quantity"], 48)
        self.assertEqual(movement["base_unit_name"], "Chupa ya Soda")
        self.assertEqual(movement["conversion_factor_used"], 24)

    def test_update_reverses_and_reapplies_converted_stock(self):
        response = self.post_sale(2, self.crate_config)
        sale = Sale.objects.get()
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(self.stock_quantity(), 192)

        update = self.client.patch(
            f"/api/sales/{sale.uuid}/",
            {
                "items": [
                    {
                        "product": str(self.product.uuid),
                        "product_unit": str(self.crate_config.uuid),
                        "quantity": 3,
                        "unit_price": "22000.00",
                    }
                ]
            },
            format="json",
        )

        self.assertEqual(update.status_code, 200, update.data)
        self.assertEqual(self.stock_quantity(), 168)

    def test_update_cannot_exceed_available_stock(self):
        self.assertEqual(self.post_sale(2, self.crate_config).status_code, 201)
        sale = Sale.objects.get()

        update = self.client.patch(
            f"/api/sales/{sale.uuid}/",
            {
                "items": [
                    {
                        "product": str(self.product.uuid),
                        "product_unit": str(self.crate_config.uuid),
                        "quantity": 11,
                        "unit_price": "22000.00",
                    }
                ]
            },
            format="json",
        )

        self.assertEqual(update.status_code, 400)
        self.assertEqual(self.stock_quantity(), 192)

    def test_cancel_returns_the_converted_base_quantity(self):
        self.assertEqual(self.post_sale(2, self.crate_config).status_code, 201)
        sale = Sale.objects.get()
        self.assertEqual(self.stock_quantity(), 192)

        response = self.client.post(f"/api/sales/{sale.uuid}/cancel/")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.stock_quantity(), 240)
        sale.refresh_from_db()
        self.assertEqual(sale.status, Sale.Status.CANCELLED)

    def test_old_sale_keeps_the_conversion_factor_used_at_the_time(self):
        self.assertEqual(self.post_sale(2, self.crate_config).status_code, 201)

        self.crate_config.conversion_factor = 30
        self.crate_config.save()

        sale = Sale.objects.get()
        detail = self.client.get(f"/api/sales/{sale.uuid}/").data
        item = detail["items"][0]
        self.assertEqual(item["conversion_factor"], 24)
        self.assertEqual(item["base_quantity"], 48)
        self.assertEqual(item["product_unit_name"], "Crate ya Soda")

    def test_receipt_uses_the_transacted_unit_not_the_base_unit(self):
        self.assertEqual(self.post_sale(2, self.crate_config).status_code, 201)
        sale = Sale.objects.get()

        receipt = self.client.get(f"/api/sales/{sale.uuid}/receipt/?format=json").data["data"]
        item = receipt["items"][0]

        self.assertEqual(str(item["quantity"]), "2")
        self.assertEqual(item["unit"], "Crate ya Soda (CS)")
        self.assertEqual(str(item["unit_price"]), "22000.00")
        self.assertEqual(str(item["line_total"]), "44000.00")
        self.assertEqual(str(receipt["totals"]["grand_total"]), "44000.00")

    def test_receipt_uses_the_base_unit_for_retail_lines(self):
        self.assertEqual(
            self.post_sale(3, self.chupa_config, "1000.00").status_code, 201
        )
        sale = Sale.objects.get()

        receipt = self.client.get(f"/api/sales/{sale.uuid}/receipt/?format=json").data["data"]
        item = receipt["items"][0]

        self.assertEqual(str(item["quantity"]), "3")
        self.assertEqual(item["unit"], "CHP")
        self.assertEqual(str(item["line_total"]), "3000.00")

    def test_stock_api_reports_base_and_human_readable_quantities(self):
        self.assertEqual(
            self.post_sale(1, self.chupa_config, "1000.00").status_code, 201
        )

        stock_data = self.client.get("/api/stocks/").data["results"][0]
        self.assertEqual(stock_data["quantity"], 239)
        self.assertEqual(stock_data["base_unit_name"], "Chupa ya Soda")
        self.assertEqual(stock_data["formatted_quantity"], "9 CS + 23 CHP")
        self.assertEqual(stock_data["base_display"], "239 CHP")

    def test_destroy_is_not_allowed(self):
        self.assertEqual(
            self.post_sale(1, self.chupa_config, "1000.00").status_code, 201
        )
        sale = Sale.objects.get()

        response = self.client.delete(f"/api/sales/{sale.uuid}/")

        self.assertEqual(response.status_code, 400)


class SaleFlowEndToEndTests(TestCase):
    """Product -> units -> stock -> availability -> sale -> receipt -> tables."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="shopkeeper@example.com",
            phone="255700000077",
            password="safe-password-123",
            role=User.Roles.MANAGER,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.customer = Customer.objects.create(name="Vendor", created_by=self.user)
        category = Category.objects.create(name="Drinks", created_by=self.user)
        brand = Brand.objects.create(name="Mirinda", category=category, created_by=self.user)
        chupa = Unit.objects.create(
            name="Chupa ya Soda", abbreviation="CHP", created_by=self.user
        )
        crate = Unit.objects.create(
            name="Crate ya Soda", abbreviation="CS", created_by=self.user
        )

    def configure_product(self):
        """The product exposes only its own units with a real conversion."""
        response = self.client.post(
            "/api/products/",
            {
                "name": "Mirinda Orange",
                "brand": str(Brand.objects.get(name="Mirinda").uuid),
                "base_unit": str(Unit.objects.get(name="Chupa ya Soda").uuid),
                "description": "",
                "buying_price": "800.00",
                "selling_price": "1000.00",
                "product_units": [
                    {
                        "unit": str(Unit.objects.get(name="Chupa ya Soda").uuid),
                        "conversion_factor": "1",
                        "buying_price": "800.00",
                        "selling_price": "1000.00",
                    },
                    {
                        "unit": str(Unit.objects.get(name="Crate ya Soda").uuid),
                        "conversion_factor": "24",
                        "buying_price": "18000.00",
                        "selling_price": "16000.00",
                    },
                ],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def test_complete_sale_flow_for_the_documented_example(self):
        product_data = self.configure_product()
        product_uuid = product_data["uuid"]
        units = {pu["unit_name"]: pu for pu in product_data["product_units"]}

        # Only the units configured for this product are offered.
        self.assertEqual(set(units), {"Chupa ya Soda", "Crate ya Soda"})
        self.assertEqual(units["Crate ya Soda"]["conversion_factor"], 24)

        # 239 base units on hand.
        from apps.stock.models import Stock

        stock = Stock.objects.get(product__uuid=product_uuid)
        stock.quantity = 239
        stock.save(update_fields=["quantity"])

        availability = self.client.get(
            f"/api/stocks/availability/?product={product_uuid}"
        ).data
        by_unit = {entry["selected_unit"]: entry for entry in availability}
        self.assertEqual(by_unit["Chupa ya Soda"]["available_display"], "239 CHP")
        self.assertEqual(
            by_unit["Crate ya Soda"]["available_display"], "9 CS + 23 CHP"
        )
        self.assertEqual(by_unit["Crate ya Soda"]["available_quantity"], 9)

        # Selling 2 crates converts to 48 base units.
        sale = self.client.post(
            "/api/sales/",
            {
                "customer": str(self.customer.uuid),
                "sale_date": timezone.now().isoformat(),
                "items": [
                    {
                        "product": product_uuid,
                        "product_unit": units["Crate ya Soda"]["uuid"],
                        "quantity": 2,
                        "unit_price": "16000.00",
                    }
                ],
            },
            format="json",
        )
        self.assertEqual(sale.status_code, 201, sale.data)
        sale_uuid = sale.data["uuid"]

        # Stock is 191 base units: 7 crates + 23 chupa.
        stock.refresh_from_db()
        self.assertEqual(stock.quantity, 191)

        item = sale.data["items"][0]
        self.assertEqual(item["quantity"], 2)
        self.assertEqual(item["conversion_factor"], 24)
        self.assertEqual(item["base_quantity"], 48)
        self.assertEqual(item["subtotal"], "32000.00")
        self.assertEqual(sale.data["total"], "32000.00")

        remaining = self.client.get(
            f"/api/stocks/availability/?product={product_uuid}"
        ).data
        by_unit = {entry["selected_unit"]: entry for entry in remaining}
        self.assertEqual(
            by_unit["Crate ya Soda"]["available_display"], "7 CS + 23 CHP"
        )
        self.assertEqual(by_unit["Chupa ya Soda"]["available_display"], "191 CHP")
        self.assertEqual(by_unit["Chupa ya Soda"]["available_quantity"], 191)

        # The receipt shows what was actually transacted.
        receipt = self.client.get(f"/api/sales/{sale_uuid}/receipt/?format=json").data["data"]
        self.assertEqual(str(receipt["items"][0]["quantity"]), "2")
        self.assertEqual(receipt["items"][0]["unit"], "Crate ya Soda (CS)")
        self.assertEqual(str(receipt["totals"]["grand_total"]), "32000.00")

        # The sales and stock tables agree with the stored base quantity.
        sale_row = self.client.get("/api/sales/").data["results"][0]
        self.assertEqual(sale_row["items"][0]["base_quantity"], 48)

        stock_row = self.client.get("/api/stocks/").data["results"][0]
        self.assertEqual(stock_row["quantity"], 191)
        self.assertEqual(stock_row["formatted_quantity"], "7 CS + 23 CHP")
        self.assertEqual(stock_row["base_display"], "191 CHP")