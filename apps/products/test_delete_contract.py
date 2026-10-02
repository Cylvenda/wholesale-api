"""Every delete in the shop must fail loudly with a reason, never as a 500.

The data model protects history with ``on_delete=PROTECT``, so deleting a
product, customer, supplier, brand, category or user that has been referenced
raises ``ProtectedError``. Before this was handled centrally, that escaped DRF
and surfaced as "Internal Server Error" with no explanation.
"""

from decimal import Decimal

from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.customers.models import Customer
from apps.products.models import Brand, Category, Product, ProductUnit, Unit
from apps.purchases.models import Purchase, PurchaseItem
from apps.sales.models import Sale, SaleItem
from apps.stock.models import Stock, StockMovement
from apps.suppliers.models import Supplier
from config.destroy import (
    blocker_payload,
    describe_blockers,
    integrity_error_message,
)


class DeleteContractTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="root@example.com",
            phone="255700000101",
            password="Root@123456",
            role=User.Roles.ADMIN,
            is_staff=True,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

        self.category = Category.objects.create(name="Drinks", created_by=self.admin)
        self.brand = Brand.objects.create(
            name="Mirinda", category=self.category, created_by=self.admin
        )
        self.unit = Unit.objects.create(
            name="Bottle", abbreviation="BTL", created_by=self.admin
        )

    def make_product(self, name, quantity=0):
        """A product exactly as the API creates it: stock row plus INITIAL move."""
        product = Product.objects.create(
            brand=self.brand,
            base_unit=self.unit,
            name=name,
            buying_price="500.00",
            selling_price="800.00",
            created_by=self.admin,
        )
        ProductUnit.objects.create(
            product=product,
            unit=self.unit,
            conversion_factor=1,
            buying_price=Decimal("500.00"),
            selling_price=Decimal("800.00"),
            created_by=self.admin,
        )
        stock = Stock.objects.create(
            product=product, quantity=quantity, created_by=self.admin
        )
        StockMovement.objects.create(
            stock=stock,
            movement_type=StockMovement.MovementTypes.INITIAL,
            notes="Initial stock",
            created_by=self.admin,
        )
        return product

    # ------------------------------------------------------------------
    # Products
    # ------------------------------------------------------------------

    def test_unused_product_is_deleted(self):
        """Creating a product always opens a Stock row; that must not block it."""
        product = self.make_product("Mirinda Lemon")

        response = self.client.delete(f"/api/products/{product.uuid}/")

        self.assertEqual(response.status_code, 204, response.data)
        self.assertFalse(Product.objects.filter(pk=product.pk).exists())
        self.assertFalse(Stock.objects.filter(product=product).exists())

    def test_product_with_stock_reports_the_quantity(self):
        product = self.make_product("Seven Up", quantity=50)

        response = self.client.delete(f"/api/products/{product.uuid}/")

        self.assertEqual(response.status_code, 400)
        message = str(response.data)
        self.assertIn("50 units still on hand", message)
        self.assertIn("inactive", message)
        self.assertTrue(Product.objects.filter(pk=product.pk).exists())
        self.assertEqual(Stock.objects.get(product=product).quantity, 50)

    def test_product_with_sales_is_not_deleted(self):
        product = self.make_product("Coke")
        customer = Customer.objects.create(name="Shop", created_by=self.admin)
        sale = Sale.objects.create(
            customer=customer,
            status=Sale.Status.COMPLETED,
            subtotal=Decimal("800.00"),
            total=Decimal("800.00"),
            sale_date=timezone.now(),
            created_by=self.admin,
        )
        SaleItem.objects.create(
            sale=sale,
            product=product,
            product_unit=product.product_units.first(),
            quantity=1,
            conversion_factor_used=1,
            base_quantity=1,
            unit_price=Decimal("800.00"),
            subtotal=Decimal("800.00"),
            unit_name="Bottle",
            unit_abbreviation="BTL",
            product_name=product.name,
            created_by=self.admin,
        )

        response = self.client.delete(f"/api/products/{product.uuid}/")

        self.assertEqual(response.status_code, 400)
        self.assertIn("recorded sales", str(response.data))
        self.assertTrue(Product.objects.filter(pk=product.pk).exists())

    def test_stocktake_movement_blocks_product_deletion(self):
        """A movement beyond the INITIAL row is real history."""
        product = self.make_product("Fanta")
        StockMovement.objects.create(
            stock=product.stock,
            movement_type=StockMovement.MovementTypes.STOCKTAKE_SURPLUS,
            quantity=5,
            base_quantity=5,
            created_by=self.admin,
        )

        response = self.client.delete(f"/api/products/{product.uuid}/")

        self.assertEqual(response.status_code, 400)
        self.assertIn("cannot be deleted", str(response.data))
        self.assertTrue(Product.objects.filter(pk=product.pk).exists())

    # ------------------------------------------------------------------
    # Master data
    # ------------------------------------------------------------------

    def test_referenced_master_data_names_its_blockers(self):
        self.make_product("Pepsi")

        brand = self.client.delete(f"/api/brands/{self.brand.uuid}/")
        category = self.client.delete(f"/api/categories/{self.category.uuid}/")
        unit = self.client.delete(f"/api/units/{self.unit.uuid}/")

        for response, label, blocker in (
            (brand, "brand", "product"),
            (category, "category", "brand"),
            (unit, "unit", "product"),
        ):
            self.assertEqual(response.status_code, 400, label)
            self.assertIn(f"This {label} cannot be deleted", str(response.data))
            self.assertIn(blocker, str(response.data))

    def test_unused_master_data_is_deleted(self):
        spare_brand = Brand.objects.create(
            name="Spare", category=self.category, created_by=self.admin
        )
        spare_category = Category.objects.create(name="Spare", created_by=self.admin)
        spare_unit = Unit.objects.create(name="Spare", abbreviation="SPR", created_by=self.admin)

        self.assertEqual(
            self.client.delete(f"/api/brands/{spare_brand.uuid}/").status_code, 204
        )
        self.assertEqual(
            self.client.delete(f"/api/categories/{spare_category.uuid}/").status_code, 204
        )
        self.assertEqual(
            self.client.delete(f"/api/units/{spare_unit.uuid}/").status_code, 204
        )

    def test_customer_with_sales_and_supplier_with_purchases_are_protected(self):
        customer = Customer.objects.create(name="Regular", created_by=self.admin)
        Sale.objects.create(
            customer=customer,
            status=Sale.Status.COMPLETED,
            subtotal=Decimal("100.00"),
            total=Decimal("100.00"),
            sale_date=timezone.now(),
            created_by=self.admin,
        )
        supplier = Supplier.objects.create(
            name="Depot", phone="255700000102", created_by=self.admin
        )
        product = self.make_product("Jumbo")
        purchase = Purchase.objects.create(
            supplier=supplier,
            status=Purchase.Status.COMPLETED,
            total=Decimal("100.00"),
            purchase_date=timezone.now(),
            created_by=self.admin,
        )
        PurchaseItem.objects.create(
            purchase=purchase,
            product=product,
            product_unit=product.product_units.first(),
            quantity=1,
            conversion_factor_used=1,
            base_quantity=1,
            unit_cost=Decimal("100.00"),
            subtotal=Decimal("100.00"),
            unit_name="Bottle",
            unit_abbreviation="BTL",
            product_name=product.name,
            created_by=self.admin,
        )

        customer_response = self.client.delete(f"/api/customers/{customer.uuid}/")
        supplier_response = self.client.delete(f"/api/suppliers/{supplier.uuid}/")

        self.assertEqual(customer_response.status_code, 400)
        self.assertIn("This customer cannot be deleted", str(customer_response.data))
        self.assertIn("sale", str(customer_response.data))

        self.assertEqual(supplier_response.status_code, 400)
        self.assertIn("This supplier cannot be deleted", str(supplier_response.data))
        self.assertIn("purchase", str(supplier_response.data))

    def test_immutable_transactions_point_at_the_cancel_action(self):
        customer = Customer.objects.create(name="Buyer", created_by=self.admin)
        sale = Sale.objects.create(
            customer=customer,
            status=Sale.Status.COMPLETED,
            subtotal=Decimal("100.00"),
            total=Decimal("100.00"),
            sale_date=timezone.now(),
            created_by=self.admin,
        )
        supplier = Supplier.objects.create(
            name="Seller", phone="255700000103", created_by=self.admin
        )
        purchase = Purchase.objects.create(
            supplier=supplier,
            status=Purchase.Status.COMPLETED,
            total=Decimal("100.00"),
            purchase_date=timezone.now(),
            created_by=self.admin,
        )

        sale_response = self.client.delete(f"/api/sales/{sale.uuid}/")
        purchase_response = self.client.delete(f"/api/purchases/{purchase.uuid}/")

        self.assertIn("cancel", str(sale_response.data))
        self.assertIn("cancel", str(purchase_response.data))
        self.assertTrue(Sale.objects.filter(pk=sale.pk).exists())
        self.assertTrue(Purchase.objects.filter(pk=purchase.pk).exists())

    # ------------------------------------------------------------------
    # Missing / malformed identifiers
    # ------------------------------------------------------------------

    def test_unknown_and_malformed_identifiers_return_404_not_500(self):
        for path in (
            "/api/products/00000000-0000-0000-0000-000000000000/",
            "/api/products/not-a-uuid/",
            "/api/products/12345/",
            "/api/users/not-a-uuid/",
            "/api/customers/12345/",
            "/api/units/not-a-uuid/",
        ):
            response = self.client.delete(path)
            self.assertEqual(response.status_code, 404, path)


class DeleteErrorHelpersTests(TestCase):
    """The helpers that turn database failures into readable sentences."""

    def test_describe_blockers_handles_model_instances(self):
        """ProtectedError stores a flat set of instances, not keys."""
        author = User.objects.create(
            email="blocker@example.com",
            phone="255700000111",
            password="Block@12345",
        )
        blockers = describe_blockers([author, author])
        self.assertEqual(blockers, ["user (x2)"])

    def test_describe_blockers_handles_model_and_pair_shapes(self):
        self.assertEqual(describe_blockers([]), [])
        self.assertEqual(describe_blockers([Product, Brand]), ["brand", "product"])
        self.assertEqual(
            describe_blockers([(Product, {1: object()}), (Product, {2: object()})]),
            ["product (x2)"],
        )

    def test_blocker_payload_reads_either_error_type(self):
        from django.db.models.deletion import ProtectedError, RestrictedError

        author = User.objects.create(
            email="payload@example.com",
            phone="255700000112",
            password="Load@12345",
        )
        self.assertEqual(blocker_payload(ProtectedError("x", {author})), {author})
        self.assertEqual(blocker_payload(RestrictedError("x", {author})), {author})
        self.assertEqual(blocker_payload(IntegrityError("x")), [])

    def test_integrity_error_messages_are_specific(self):
        unique = IntegrityError("UNIQUE constraint failed: products_brand.name")
        foreign = IntegrityError("FOREIGN KEY constraint failed")

        self.assertIn("unique", integrity_error_message(unique).lower())
        self.assertIn("depend on it", integrity_error_message(foreign).lower())
        self.assertTrue(integrity_error_message(IntegrityError("boom")))