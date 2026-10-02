from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.customers.models import Customer
from apps.products.models import Brand, Category, Product, ProductUnit, Unit
from apps.purchases.models import Purchase, PurchaseItem
from apps.sales.models import Sale, SaleItem
from apps.stock.models import Stock
from apps.suppliers.models import Supplier


class ProductUnitConfigurationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="unit-admin@example.com",
            phone="255700000031",
            password="safe-password-123",
            role=User.Roles.MANAGER,
        )
        self.category = Category.objects.create(name="Beverages", created_by=self.user)
        self.brand = Brand.objects.create(
            name="Soda Brand", category=self.category, created_by=self.user
        )
        self.bottle = Unit.objects.create(
            name="Bottle", abbreviation="BTL", created_by=self.user
        )
        self.crate = Unit.objects.create(
            name="Crate", abbreviation="CRT", created_by=self.user
        )
        self.product = Product.objects.create(
            brand=self.brand,
            base_unit=self.bottle,
            name="Orange Soda",
            buying_price=Decimal("800.00"),
            selling_price=Decimal("1000.00"),
            created_by=self.user,
        )
        self.bottle_config = ProductUnit.objects.create(
            product=self.product,
            unit=self.bottle,
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

    def test_product_api_exposes_base_unit_and_configured_units(self):
        data = self.client.get(f"/api/products/{self.product.uuid}/").data

        self.assertEqual(str(data["base_unit"]), str(self.bottle.uuid))
        self.assertEqual(data["base_unit_name"], "Bottle")
        self.assertEqual(data["base_unit_abbreviation"], "BTL")
        self.assertEqual(len(data["product_units"]), 2)

        by_unit = {str(pu["unit"]): pu for pu in data["product_units"]}
        self.assertEqual(by_unit[str(self.crate.uuid)]["conversion_factor"], 24)
        self.assertEqual(by_unit[str(self.crate.uuid)]["buying_price"], "18000.00")
        self.assertEqual(by_unit[str(self.crate.uuid)]["selling_price"], "22000.00")

    def test_product_unit_cannot_be_duplicated_for_the_same_product(self):
        duplicate = ProductUnit(
            product=self.product,
            unit=self.crate,
            conversion_factor=30,
            buying_price=Decimal("1.00"),
            selling_price=Decimal("2.00"),
            created_by=self.user,
        )

        with self.assertRaises(Exception):
            duplicate.save()

    def test_conversion_factor_must_be_greater_than_zero(self):
        with self.assertRaises(Exception):
            ProductUnit.objects.create(
                product=self.product,
                unit=Unit.objects.create(name="Box", created_by=self.user),
                conversion_factor=0,
                buying_price=Decimal("1.00"),
                selling_price=Decimal("2.00"),
                created_by=self.user,
            )

    def test_base_unit_must_keep_a_conversion_factor_of_one(self):
        with self.assertRaises(Exception):
            ProductUnit.objects.create(
                product=self.product,
                unit=self.bottle,
                conversion_factor=6,
                buying_price=Decimal("800.00"),
                selling_price=Decimal("1000.00"),
                created_by=self.user,
            )

    def test_creating_a_product_with_its_unit_table(self):
        response = self.client.post(
            "/api/products/",
            {
                "name": "Fanta",
                "brand": str(self.brand.uuid),
                "base_unit": str(self.bottle.uuid),
                "description": "",
                "buying_price": "700.00",
                "selling_price": "900.00",
                "product_units": [
                    {
                        "unit": str(self.bottle.uuid),
                        "conversion_factor": "1",
                        "buying_price": "700.00",
                        "selling_price": "900.00",
                    },
                    {
                        "unit": str(self.crate.uuid),
                        "conversion_factor": "24",
                        "buying_price": "16000.00",
                        "selling_price": "20000.00",
                    },
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        created = Product.objects.get(name="Fanta")
        self.assertEqual(created.base_unit, self.bottle)
        self.assertEqual(created.product_units.count(), 2)

        crate_row = created.product_units.get(unit=self.crate)
        self.assertEqual(crate_row.conversion_factor, 24)
        self.assertEqual(crate_row.selling_price, Decimal("20000.00"))

    def test_prices_can_differ_per_unit_without_touching_stock(self):
        response = self.client.patch(
            f"/api/products/{self.product.uuid}/units/{self.crate_config.uuid}/",
            {
                "conversion_factor": "24",
                "buying_price": "19000.00",
                "selling_price": "25000.00",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.crate_config.refresh_from_db()
        self.assertEqual(self.crate_config.selling_price, Decimal("25000.00"))
        # Stock is untouched by a price change.
        self.assertEqual(Stock.objects.get(product=self.product).quantity, 240)

    def test_reconfiguring_a_unit_does_not_rewrite_historical_transactions(self):
        """Case 7: a 24-bottle crate sold earlier stays 24 bottles."""
        supplier = Supplier.objects.create(
            name="Soda Supplier", phone="255700000032", created_by=self.user
        )
        purchase = Purchase.objects.create(
            supplier=supplier,
            purchase_date=timezone.now(),
            status=Purchase.Status.COMPLETED,
            created_by=self.user,
        )
        PurchaseItem.objects.create(
            purchase=purchase,
            product=self.product,
            product_unit=self.crate_config,
            quantity=2,
            conversion_factor_used=24,
            base_quantity=48,
            unit_cost=Decimal("18000.00"),
            subtotal=Decimal("36000.00"),
            unit_name="Crate",
            unit_abbreviation="CRT",
            product_name="Orange Soda",
            created_by=self.user,
        )

        self.crate_config.conversion_factor = 30
        self.crate_config.save()

        item = PurchaseItem.objects.get()
        self.assertEqual(item.conversion_factor_used, 24)
        self.assertEqual(item.base_quantity, 48)

        detail = self.client.get(f"/api/purchases/{purchase.uuid}/").data
        self.assertEqual(detail["items"][0]["conversion_factor"], 24)
        self.assertEqual(detail["items"][0]["base_quantity"], 48)

    def test_deleting_a_unit_used_by_a_product_is_protected(self):
        response = self.client.delete(f"/api/units/{self.crate.uuid}/")

        self.assertEqual(response.status_code, 400)
        self.assertTrue(Unit.objects.filter(uuid=self.crate.uuid).exists())

    def test_unit_in_use_can_be_deactivated_instead(self):
        response = self.client.patch(
            f"/api/units/{self.crate.uuid}/",
            {"name": "Crate", "abbreviation": "CRT", "is_active": False},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(Unit.objects.get(uuid=self.crate.uuid).is_active)

    def test_duplicate_unit_names_are_rejected(self):
        response = self.client.post(
            "/api/units/",
            {"name": "Bottle", "abbreviation": "B"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_transaction_items_snapshot_the_product_and_unit_names(self):
        """Renaming a product or unit later must not rewrite what old records show."""
        customer = Customer.objects.create(name="Buyer", created_by=self.user)
        sale = Sale.objects.create(
            customer=customer,
            sale_date=timezone.now(),
            status=Sale.Status.COMPLETED,
            created_by=self.user,
        )
        SaleItem.objects.create(
            sale=sale,
            product=self.product,
            product_unit=self.crate_config,
            sale_type="wholesale",
            quantity=1,
            conversion_factor_used=24,
            base_quantity=24,
            unit_price=Decimal("22000.00"),
            subtotal=Decimal("22000.00"),
            unit_name="Crate",
            unit_abbreviation="CRT",
            product_name="Orange Soda",
            created_by=self.user,
        )

        self.product.name = "Orange Soda XL"
        self.product.save()
        self.crate.name = "Crate of 24"
        self.crate.save()

        detail = self.client.get(f"/api/sales/{sale.uuid}/").data
        item = detail["items"][0]
        self.assertEqual(item["product_name"], "Orange Soda")
        self.assertEqual(item["product_unit_name"], "Crate")