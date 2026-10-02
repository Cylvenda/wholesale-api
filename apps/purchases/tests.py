from decimal import Decimal
from unittest import mock

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.purchases import serializers as serializers_module
from apps.products.models import Brand, Category, Product, ProductUnit, Unit
from apps.stock.models import Stock
from apps.suppliers.models import Supplier
from .models import Purchase, PurchaseItem


class PurchaseAPITests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="buyer@example.com",
            phone="255700000002",
            password="safe-password-123",
            role=User.Roles.MANAGER,
        )
        self.category = Category.objects.create(name="Beer", created_by=self.user)
        self.brand = Brand.objects.create(
            name="Kilimanjaro", category=self.category, created_by=self.user
        )
        self.bottle = Unit.objects.create(
            name="Bottle", abbreviation="BTL", created_by=self.user
        )
        self.product = Product.objects.create(
            brand=self.brand,
            base_unit=self.bottle,
            name="Safari Lager 500ml",
            buying_price=Decimal("1000.00"),
            selling_price=Decimal("1500.00"),
            created_by=self.user,
        )
        self.bottle_config = ProductUnit.objects.create(
            product=self.product,
            unit=self.bottle,
            conversion_factor=1,
            buying_price=Decimal("1000.00"),
            selling_price=Decimal("1500.00"),
            created_by=self.user,
        )
        self.crate = Unit.objects.create(
            name="Crate", abbreviation="CRT", created_by=self.user
        )
        self.crate_config = ProductUnit.objects.create(
            product=self.product,
            unit=self.crate,
            conversion_factor=24,
            buying_price=Decimal("18000.00"),
            selling_price=Decimal("22000.00"),
            created_by=self.user,
        )
        Stock.objects.create(product=self.product, created_by=self.user)
        self.supplier = Supplier.objects.create(
            name="Kilimanjaro Breweries",
            phone="255712000151",
            created_by=self.user,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def post_purchase(self, quantity, product_unit, unit_cost="18000.00"):
        return self.client.post(
            "/api/purchases/",
            {
                "supplier": str(self.supplier.uuid),
                "invoice_number": "PUR-001",
                "purchase_date": timezone.now().isoformat(),
                "items": [
                    {
                        "product": str(self.product.uuid),
                        "product_unit": str(product_unit.uuid),
                        "quantity": quantity,
                        "unit_cost": unit_cost,
                    }
                ],
            },
            format="json",
        )

    def test_purchase_in_crates_adds_converted_base_quantity(self):
        """Case 1: 10 crates of 24 bottles yields 240 bottles in stock."""
        response = self.post_purchase(10, self.crate_config)

        self.assertEqual(response.status_code, 201, response.data)
        purchase = Purchase.objects.get()
        self.assertEqual(purchase.total, Decimal("180000.00"))
        self.assertEqual(purchase.status, Purchase.Status.COMPLETED)

        item = PurchaseItem.objects.get()
        self.assertEqual(item.quantity, 10)
        self.assertEqual(item.base_quantity, 240)
        self.assertEqual(item.conversion_factor_used, 24)
        self.assertEqual(item.unit_name, "Crate")

        stock = Stock.objects.get(product=self.product)
        self.assertEqual(stock.quantity, 240)

        stock_data = self.client.get("/api/stocks/").data["results"][0]
        self.assertEqual(stock_data["quantity"], 240)
        self.assertEqual(stock_data["base_unit_name"], "Bottle")
        self.assertEqual(stock_data["formatted_quantity"], "10 CRT")

    def test_five_crates_convert_to_one_hundred_and_twenty(self):
        """Case 3: 5 crates x 24 bottles = 120 base units on hand."""
        response = self.post_purchase(5, self.crate_config)

        self.assertEqual(response.status_code, 201, response.data)
        item = PurchaseItem.objects.get()
        self.assertEqual(item.quantity, 5)
        self.assertEqual(item.conversion_factor_used, 24)
        self.assertEqual(item.base_quantity, 120)
        self.assertEqual(item.subtotal, Decimal("90000.00"))
        self.assertEqual(Stock.objects.get(product=self.product).quantity, 120)

    def test_a_failing_item_rolls_back_the_whole_purchase(self):
        """Case 16: stock and rows move together or not at all."""
        other_product = Product.objects.create(
            brand=self.brand,
            base_unit=self.bottle,
            name="Rollback Beer",
            buying_price=Decimal("900.00"),
            selling_price=Decimal("1400.00"),
            created_by=self.user,
        )
        ProductUnit.objects.create(
            product=other_product,
            unit=self.bottle,
            conversion_factor=1,
            buying_price=Decimal("900.00"),
            selling_price=Decimal("1400.00"),
            created_by=self.user,
        )
        Stock.objects.create(product=other_product, created_by=self.user)

        payload = {
            "supplier": str(self.supplier.uuid),
            "purchase_date": timezone.now().isoformat(),
            "items": [
                {
                    "product": str(self.product.uuid),
                    "product_unit": str(self.crate_config.uuid),
                    "quantity": 10,
                    "unit_cost": "18000.00",
                },
                {
                    "product": str(other_product.uuid),
                    "product_unit": str(other_product.product_units.first().uuid),
                    "quantity": 4,
                    "unit_cost": "900.00",
                },
            ],
        }

        # The second add_stock fails after the first has already credited stock.
        original_add_stock = serializers_module.add_stock
        calls = {"count": 0}

        def flaky_add_stock(**kwargs):
            calls["count"] += 1
            if calls["count"] == 2:
                raise ValueError("Stock write failed")
            return original_add_stock(**kwargs)

        with mock.patch(
            "apps.purchases.serializers.add_stock", side_effect=flaky_add_stock
        ):
            response = self.client.post("/api/purchases/", payload, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(calls["count"], 2)
        # Nothing survives: no purchase, no rows, no stock from the first item.
        self.assertEqual(Purchase.objects.count(), 0)
        self.assertEqual(PurchaseItem.objects.count(), 0)
        self.assertEqual(Stock.objects.get(product=self.product).quantity, 0)
        self.assertEqual(Stock.objects.get(product=other_product).quantity, 0)

    def test_movement_records_both_transaction_and_base_quantity(self):
        self.post_purchase(10, self.crate_config)

        movement = self.client.get("/api/stock-movements/").data["results"][0]
        self.assertEqual(movement["transaction_quantity"], 10)
        self.assertEqual(movement["transaction_unit_name"], "Crate")
        self.assertEqual(movement["base_quantity"], 240)
        self.assertEqual(movement["base_unit_name"], "Bottle")
        self.assertEqual(movement["conversion_factor_used"], 24)

    def test_retail_purchase_uses_the_base_unit(self):
        response = self.post_purchase(5, self.bottle_config, unit_cost="1000.00")

        self.assertEqual(response.status_code, 201, response.data)
        item = PurchaseItem.objects.get()
        self.assertEqual(item.base_quantity, 5)
        self.assertEqual(Stock.objects.get(product=self.product).quantity, 5)

    def test_fractional_quantities_are_rejected_for_every_unit(self):
        """Case 8 of the spec: this shop never buys fractional units."""
        response = self.post_purchase("1.5", self.crate_config)

        self.assertEqual(response.status_code, 400)
        self.assertIn("whole number", str(response.data))
        self.assertEqual(Stock.objects.get(product=self.product).quantity, 0)

        kg = Unit.objects.create(name="Kilogram", abbreviation="KG", created_by=self.user)
        kg_config = ProductUnit.objects.create(
            product=self.product,
            unit=kg,
            conversion_factor=1,
            buying_price=Decimal("5000.00"),
            selling_price=Decimal("7000.00"),
            created_by=self.user,
        )

        response = self.post_purchase("1.5", kg_config, unit_cost="5000.00")

        self.assertEqual(response.status_code, 400)
        self.assertIn("whole number", str(response.data))
        self.assertEqual(Stock.objects.get(product=self.product).quantity, 0)
        self.assertEqual(PurchaseItem.objects.count(), 0)

    def test_unit_not_configured_for_the_product_is_rejected(self):
        """Case 6-style: a unit configured on another product cannot be used here."""
        other_product = Product.objects.create(
            brand=self.brand,
            base_unit=self.bottle,
            name="Other Beer",
            buying_price=Decimal("900.00"),
            selling_price=Decimal("1400.00"),
            created_by=self.user,
        )
        foreign_unit = ProductUnit.objects.create(
            product=other_product,
            unit=self.crate,
            conversion_factor=20,
            buying_price=Decimal("15000.00"),
            selling_price=Decimal("19000.00"),
            created_by=self.user,
        )

        response = self.post_purchase(1, foreign_unit)

        self.assertEqual(response.status_code, 400)
        self.assertIn("not configured for this product", str(response.data))

    def test_conversion_is_product_specific(self):
        """Case 6: the same global Crate unit converts differently per product."""
        other_product = Product.objects.create(
            brand=self.brand,
            base_unit=self.bottle,
            name="Twenty Pack Beer",
            buying_price=Decimal("900.00"),
            selling_price=Decimal("1400.00"),
            created_by=self.user,
        )
        ProductUnit.objects.create(
            product=other_product,
            unit=self.bottle,
            conversion_factor=1,
            buying_price=Decimal("900.00"),
            selling_price=Decimal("1400.00"),
            created_by=self.user,
        )
        twenty_config = ProductUnit.objects.create(
            product=other_product,
            unit=self.crate,
            conversion_factor=20,
            buying_price=Decimal("15000.00"),
            selling_price=Decimal("19000.00"),
            created_by=self.user,
        )
        Stock.objects.create(product=other_product, created_by=self.user)

        self.assertEqual(self.post_purchase(10, self.crate_config).status_code, 201)
        self.assertEqual(Stock.objects.get(product=self.product).quantity, 240)

        response = self.client.post(
            "/api/purchases/",
            {
                "supplier": str(self.supplier.uuid),
                "purchase_date": timezone.now().isoformat(),
                "items": [
                    {
                        "product": str(other_product.uuid),
                        "product_unit": str(twenty_config.uuid),
                        "quantity": 10,
                        "unit_cost": "15000.00",
                    }
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(Stock.objects.get(product=other_product).quantity, 200)

    def test_historical_line_keeps_its_conversion_factor(self):
        """Case 7: reconfiguring the crate later does not rewrite old lines."""
        self.post_purchase(10, self.crate_config)

        self.crate_config.conversion_factor = 30
        self.crate_config.save()

        item = PurchaseItem.objects.get()
        self.assertEqual(item.conversion_factor_used, 24)
        self.assertEqual(item.base_quantity, 240)

        detail = self.client.get(f"/api/purchases/{item.purchase.uuid}/").data
        self.assertEqual(detail["items"][0]["conversion_factor"], 24)

    def test_destroy_is_not_allowed(self):
        purchase = Purchase.objects.create(
            supplier=self.supplier,
            total=Decimal("0.00"),
            purchase_date=timezone.now(),
            status=Purchase.Status.COMPLETED,
            created_by=self.user,
        )

        response = self.client.delete(f"/api/purchases/{purchase.uuid}/")

        self.assertEqual(response.status_code, 400)

    def test_cancel_reverses_converted_stock(self):
        from apps.stock.models import StockMovement
        from apps.stock.services import add_stock

        add_stock(
            product=self.product,
            base_quantity=10,
            movement_type=StockMovement.MovementTypes.PURCHASES,
            reference="initial",
            note="Initial test stock",
            user=self.user,
        )

        self.assertEqual(self.post_purchase(2, self.crate_config).status_code, 201)
        self.assertEqual(Stock.objects.get(product=self.product).quantity, 58)

        purchase = Purchase.objects.get()
        response = self.client.post(f"/api/purchases/{purchase.uuid}/cancel/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Stock.objects.get(product=self.product).quantity, 10)
        purchase.refresh_from_db()
        self.assertEqual(purchase.status, Purchase.Status.CANCELLED)