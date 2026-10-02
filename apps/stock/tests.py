from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.products.models import Brand, Category, Product, ProductUnit, Unit
from .models import Stock


class StockMovementQuantityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="stockkeeper@example.com",
            phone="255700000009",
            password="safe-password-123",
            role=User.Roles.STOREKEEPER,
        )
        category = Category.objects.create(name="Drinks", created_by=self.user)
        self.brand = Brand.objects.create(
            name="Fanta Brand", category=category, created_by=self.user
        )
        self.bottle = Unit.objects.create(
            name="Bottle", abbreviation="BTL", created_by=self.user
        )
        self.product = Product.objects.create(
            brand=self.brand,
            base_unit=self.bottle,
            name="Fanta",
            buying_price=Decimal("1000.00"),
            selling_price=Decimal("1500.00"),
            created_by=self.user,
        )
        ProductUnit.objects.create(
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
            buying_price=Decimal("20000.00"),
            selling_price=Decimal("26000.00"),
            created_by=self.user,
        )
        Stock.objects.create(product=self.product, quantity=300, created_by=self.user)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def adjust(self, **overrides):
        payload = {
            "product": str(self.product.uuid),
            "movement_type": "Stocktake Surplus",
            "quantity": 1,
        }
        payload.update(overrides)
        return self.client.post("/api/stock-movements/", payload, format="json")

    def test_decrease_above_available_stock_returns_quantity_error(self):
        response = self.client.post(
            "/api/stock-movements/",
            {
                "product": str(self.product.uuid),
                "movement_type": "Stocktake Loss",
                "quantity": 400,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn(
            "Insufficient stock for Fanta.", response.data["data"]["quantity"]
        )
        self.assertEqual(Stock.objects.get(product=self.product).quantity, 300)

    def test_manual_stocktake_surplus_returns_the_created_movement(self):
        response = self.client.post(
            "/api/stock-movements/",
            {
                "product": str(self.product.uuid),
                "movement_type": "Stocktake Surplus",
                "quantity": 2,
                "notes": "Damaged stock found",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(str(response.data["quantity"]), "2")
        self.assertEqual(response.data["product_name"], "Fanta")
        self.assertEqual(response.data["base_unit_name"], "Bottle")
        self.assertEqual(Stock.objects.get(product=self.product).quantity, 302)

    def test_manual_stocktake_loss_returns_the_created_movement(self):
        response = self.client.post(
            "/api/stock-movements/",
            {
                "product": str(self.product.uuid),
                "movement_type": "Stocktake Loss",
                "quantity": 1,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(str(response.data["quantity"]), "1")
        self.assertEqual(Stock.objects.get(product=self.product).quantity, 299)

    def test_stock_api_formats_mixed_pack_and_base_quantities(self):
        stock_data = self.client.get("/api/stocks/").data["results"][0]
        self.assertEqual(stock_data["quantity"], 300)
        self.assertEqual(stock_data["formatted_quantity"], "12 CRT + 12 BTL")
        self.assertEqual(stock_data["base_unit_name"], "Bottle")
        self.assertEqual(stock_data["base_unit_abbreviation"], "BTL")

        Stock.objects.filter(product=self.product).update(quantity=239)
        stock_data = self.client.get("/api/stocks/").data["results"][0]
        self.assertEqual(stock_data["formatted_quantity"], "9 CRT + 23 BTL")

    def test_stock_api_exposes_the_product_uuid_for_client_lookups(self):
        """The sale form matches stock rows to products by uuid, not by row id."""
        stock_data = self.client.get("/api/stocks/").data["results"][0]

        self.assertEqual(str(stock_data["product"]), str(self.product.uuid))
        self.assertEqual(stock_data["product_name"], "Fanta")
        self.assertEqual(stock_data["quantity"], 300)

    def test_stock_summary_uses_base_unit_quantity(self):
        summary = self.client.get("/api/stocks/summary/").data
        self.assertEqual(summary["total_quantity"], 300)
        self.assertEqual(str(summary["stock_value"]), "300000.00")

    def test_surplus_counted_in_crates_converts_to_base_units(self):
        response = self.adjust(
            product_unit=str(self.crate_config.uuid),
            quantity=3,
            notes="Crates found in the back store",
        )

        self.assertEqual(response.status_code, 201, response.data)
        # 3 crates x 24 bottles = 72 bottles on top of the 300 already there.
        self.assertEqual(Stock.objects.get(product=self.product).quantity, 372)
        self.assertEqual(response.data["transaction_quantity"], 3)
        self.assertEqual(response.data["transaction_unit_name"], "Crate")
        self.assertEqual(response.data["conversion_factor_used"], 24)
        self.assertEqual(response.data["base_quantity"], 72)
        self.assertEqual(response.data["base_unit_name"], "Bottle")

    def test_loss_counted_in_crates_removes_converted_base_units(self):
        response = self.adjust(
            movement_type="Stocktake Loss",
            product_unit=str(self.crate_config.uuid),
            quantity=2,
        )

        self.assertEqual(response.status_code, 201, response.data)
        # 2 crates x 24 bottles = 48 bottles off the 300 on hand.
        self.assertEqual(Stock.objects.get(product=self.product).quantity, 252)
        self.assertEqual(response.data["transaction_quantity"], 2)
        self.assertEqual(response.data["conversion_factor_used"], 24)
        self.assertEqual(response.data["base_quantity"], 48)

    def test_adjustment_in_the_base_unit_is_one_to_one(self):
        response = self.adjust(
            product_unit=str(self.product.product_units.get(unit=self.bottle).uuid),
            quantity=5,
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(Stock.objects.get(product=self.product).quantity, 305)
        self.assertEqual(response.data["base_quantity"], 5)
        self.assertEqual(response.data["conversion_factor_used"], 1)

    def test_omitting_the_unit_falls_back_to_the_base_unit(self):
        response = self.adjust(quantity=4)

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(Stock.objects.get(product=self.product).quantity, 304)
        self.assertEqual(response.data["transaction_unit_name"], "Bottle")
        self.assertEqual(response.data["base_quantity"], 4)

    def test_unit_configured_for_another_product_is_rejected(self):
        other_product = Product.objects.create(
            brand=self.brand,
            base_unit=self.bottle,
            name="Sprite",
            buying_price=Decimal("1000.00"),
            selling_price=Decimal("1500.00"),
            created_by=self.user,
        )
        foreign = ProductUnit.objects.create(
            product=other_product,
            unit=self.crate,
            conversion_factor=20,
            buying_price=Decimal("17000.00"),
            selling_price=Decimal("22000.00"),
            created_by=self.user,
        )

        response = self.adjust(product_unit=str(foreign.uuid), quantity=2)

        self.assertEqual(response.status_code, 400)
        self.assertIn("not configured for this product", str(response.data))
        self.assertEqual(Stock.objects.get(product=self.product).quantity, 300)

    def test_fractional_adjustment_quantities_are_rejected(self):
        response = self.adjust(
            product_unit=str(self.crate_config.uuid), quantity="1.5"
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("whole number", str(response.data))
        self.assertEqual(Stock.objects.get(product=self.product).quantity, 300)

    def test_each_product_uses_its_own_conversion_factor(self):
        other_product = Product.objects.create(
            brand=self.brand,
            base_unit=self.bottle,
            name="Sprite",
            buying_price=Decimal("1000.00"),
            selling_price=Decimal("1500.00"),
            created_by=self.user,
        )
        ProductUnit.objects.create(
            product=other_product,
            unit=self.bottle,
            conversion_factor=1,
            buying_price=Decimal("1000.00"),
            selling_price=Decimal("1500.00"),
            created_by=self.user,
        )
        twenty = ProductUnit.objects.create(
            product=other_product,
            unit=self.crate,
            conversion_factor=20,
            buying_price=Decimal("17000.00"),
            selling_price=Decimal("22000.00"),
            created_by=self.user,
        )
        Stock.objects.create(product=other_product, created_by=self.user)

        response = self.adjust(
            product=str(other_product.uuid),
            product_unit=str(twenty.uuid),
            quantity=4,
        )

        self.assertEqual(response.status_code, 201, response.data)
        # 4 crates of 20 = 80 bottles, not 96: no global crate size.
        self.assertEqual(Stock.objects.get(product=other_product).quantity, 80)
