from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.customers.models import Customer
from apps.products.models import Brand, Category, Product, ProductUnit, Unit
from apps.purchases.models import Purchase, PurchaseItem
from apps.sales.models import Sale, SaleItem
from apps.suppliers.models import Supplier


class ReceiptAPITests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="receipts@example.com",
            phone="255700000003",
            password="safe-password-123",
        )
        category = Category.objects.create(name="Drinks", created_by=self.user)
        self.brand = Brand.objects.create(
            name="Sample", category=category, created_by=self.user
        )
        self.piece = Unit.objects.create(
            name="Piece", abbreviation="PC", created_by=self.user
        )
        self.carton = Unit.objects.create(
            name="Carton", abbreviation="CTN", created_by=self.user
        )
        self.product = Product.objects.create(
            brand=self.brand,
            base_unit=self.piece,
            name="Long Product Name That Still Wraps Normally",
            buying_price=Decimal("8.00"),
            selling_price=Decimal("10.00"),
            created_by=self.user,
        )
        self.piece_config = ProductUnit.objects.create(
            product=self.product,
            unit=self.piece,
            conversion_factor=1,
            buying_price=Decimal("8.00"),
            selling_price=Decimal("10.00"),
            created_by=self.user,
        )
        self.carton_config = ProductUnit.objects.create(
            product=self.product,
            unit=self.carton,
            conversion_factor=24,
            buying_price=Decimal("160.00"),
            selling_price=Decimal("200.00"),
            created_by=self.user,
        )
        self.customer = Customer.objects.create(name="ABC Shop", created_by=self.user)
        self.supplier = Supplier.objects.create(
            name="ABC Distributors",
            phone="255712000153",
            created_by=self.user,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def create_sale(self, *, product_unit, quantity, unit_price, subtotal, sale_type="wholesale"):
        sale = Sale.objects.create(
            customer=self.customer,
            sale_date=timezone.now(),
            subtotal=subtotal,
            discount=Decimal("2.00"),
            total=subtotal - Decimal("2.00"),
            status=Sale.Status.COMPLETED,
            created_by=self.user,
        )
        SaleItem.objects.create(
            sale=sale,
            product=self.product,
            product_unit=product_unit,
            sale_type=sale_type,
            quantity=quantity,
            conversion_factor_used=product_unit.conversion_factor,
            base_quantity=quantity * product_unit.conversion_factor,
            unit_price=unit_price,
            subtotal=subtotal,
            unit_name=product_unit.unit.name,
            unit_abbreviation=product_unit.unit.abbreviation or "",
            product_name=self.product.name,
            created_by=self.user,
        )
        return sale

    def test_completed_sale_receipt_uses_sequential_number_and_bill_discount(self):
        sale = self.create_sale(
            product_unit=self.piece_config,
            quantity=2,
            unit_price=Decimal("10.00"),
            subtotal=Decimal("20.00"),
            sale_type="retail",
        )

        response = self.client.get(f"/api/sales/{sale.uuid}/receipt/?format=json")

        self.assertEqual(response.status_code, 200)
        receipt = response.data["data"]
        self.assertEqual(receipt["sale"]["receipt_number"], f"SAL-{sale.pk:06d}")
        self.assertEqual(receipt["items"][0]["unit"], "PC")
        self.assertNotIn("discount", receipt["items"][0])
        self.assertEqual(receipt["items"][0]["line_total"], Decimal("20.00"))
        self.assertEqual(receipt["totals"]["discount"], Decimal("2.00"))

    def test_wholesale_receipt_shows_cartons_not_base_pieces(self):
        sale = self.create_sale(
            product_unit=self.carton_config,
            quantity=2,
            unit_price=Decimal("200.00"),
            subtotal=Decimal("400.00"),
        )

        receipt = self.client.get(
            f"/api/sales/{sale.uuid}/receipt/?format=json"
        ).data["data"]
        item = receipt["items"][0]

        self.assertEqual(item["quantity"], 2)
        self.assertEqual(item["unit"], "Carton (CTN)")
        self.assertEqual(item["unit_price"], Decimal("200.00"))
        self.assertEqual(item["line_total"], Decimal("400.00"))
        # Not 48 pieces at a reconstructed per-piece price.
        self.assertNotEqual(item["unit_price"], Decimal("400.00") / 48)

    def test_receipt_reports_transaction_totals_not_reconstructed_prices(self):
        sale = self.create_sale(
            product_unit=self.carton_config,
            quantity=3,
            unit_price=Decimal("200.00"),
            subtotal=Decimal("600.00"),
        )

        receipt = self.client.get(
            f"/api/sales/{sale.uuid}/receipt/?format=json"
        ).data["data"]

        self.assertEqual(receipt["totals"]["subtotal"], Decimal("600.00"))
        self.assertEqual(receipt["totals"]["grand_total"], Decimal("598.00"))

    def test_completed_purchase_receipt_contains_received_goods(self):
        purchase = Purchase.objects.create(
            supplier=self.supplier,
            invoice_number="SUP-INV-17",
            purchase_date=timezone.now(),
            total=Decimal("160.00"),
            status=Purchase.Status.COMPLETED,
            created_by=self.user,
        )
        PurchaseItem.objects.create(
            purchase=purchase,
            product=self.product,
            product_unit=self.carton_config,
            quantity=1,
            conversion_factor_used=24,
            base_quantity=24,
            unit_cost=Decimal("160.00"),
            subtotal=Decimal("160.00"),
            unit_name="Carton",
            unit_abbreviation="CTN",
            product_name=self.product.name,
            created_by=self.user,
        )

        response = self.client.get(
            f"/api/purchases/{purchase.uuid}/receipt/?format=json"
        )

        self.assertEqual(response.status_code, 200)
        receipt = response.data["data"]
        self.assertEqual(
            receipt["purchase"]["receipt_number"], f"PUR-{purchase.pk:06d}"
        )
        self.assertEqual(receipt["purchase"]["supplier_invoice_number"], "SUP-INV-17")
        self.assertEqual(receipt["items"][0]["unit"], "Carton (CTN)")
        self.assertEqual(receipt["items"][0]["line_total"], Decimal("160.00"))
        self.assertEqual(receipt["totals"]["grand_total"], Decimal("160.00"))
        self.assertNotIn("payments", receipt)

    def test_cancelled_transactions_cannot_generate_receipts(self):
        sale = Sale.objects.create(
            customer=self.customer,
            sale_date=timezone.now(),
            status=Sale.Status.CANCELLED,
            created_by=self.user,
        )
        purchase = Purchase.objects.create(
            supplier=self.supplier,
            purchase_date=timezone.now(),
            status=Purchase.Status.CANCELLED,
            created_by=self.user,
        )

        sale_response = self.client.get(f"/api/sales/{sale.uuid}/receipt/?format=json")
        purchase_response = self.client.get(
            f"/api/purchases/{purchase.uuid}/receipt/?format=json"
        )

        self.assertEqual(sale_response.status_code, 400)
        self.assertEqual(purchase_response.status_code, 400)

    def test_receipt_downloads_return_thermal_pdfs(self):
        sale = Sale.objects.create(
            customer=self.customer,
            sale_date=timezone.now(),
            status=Sale.Status.COMPLETED,
            created_by=self.user,
        )
        purchase = Purchase.objects.create(
            supplier=self.supplier,
            purchase_date=timezone.now(),
            status=Purchase.Status.COMPLETED,
            created_by=self.user,
        )

        sale_response = self.client.get(f"/api/sales/{sale.uuid}/receipt/")
        purchase_response = self.client.get(f"/api/purchases/{purchase.uuid}/receipt/")

        self.assertEqual(sale_response["Content-Type"], "application/pdf")
        self.assertIn(b"%PDF", sale_response.content[:8])
        self.assertEqual(purchase_response["Content-Type"], "application/pdf")
        self.assertIn(b"%PDF", purchase_response.content[:8])


class UnitAwareReportTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="reports@example.com",
            phone="255700000042",
            password="safe-password-123",
        )
        category = Category.objects.create(name="Drinks", created_by=self.user)
        brand = Brand.objects.create(name="Report Brand", category=category, created_by=self.user)
        self.bottle = Unit.objects.create(name="Bottle", abbreviation="BTL", created_by=self.user)
        self.crate = Unit.objects.create(name="Crate", abbreviation="CRT", created_by=self.user)
        self.product = Product.objects.create(
            brand=brand,
            base_unit=self.bottle,
            name="Cola",
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
        self.customer = Customer.objects.create(name="Buyer", created_by=self.user)
        self.supplier = Supplier.objects.create(
            name="Supplier", phone="255700000043", created_by=self.user
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_sales_export_uses_the_transaction_unit_and_price(self):
        sale = Sale.objects.create(
            customer=self.customer,
            sale_date=timezone.now(),
            subtotal=Decimal("44000.00"),
            total=Decimal("44000.00"),
            status=Sale.Status.COMPLETED,
            created_by=self.user,
        )
        SaleItem.objects.create(
            sale=sale,
            product=self.product,
            product_unit=self.crate_config,
            sale_type="wholesale",
            quantity=2,
            conversion_factor_used=24,
            base_quantity=48,
            unit_price=Decimal("22000.00"),
            subtotal=Decimal("44000.00"),
            unit_name="Crate",
            unit_abbreviation="CRT",
            product_name="Cola",
            created_by=self.user,
        )

        response = self.client.get("/api/reports/sales/export/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    def test_purchases_export_returns_a_workbook(self):
        purchase = Purchase.objects.create(
            supplier=self.supplier,
            purchase_date=timezone.now(),
            total=Decimal("36000.00"),
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
            product_name="Cola",
            created_by=self.user,
        )

        response = self.client.get("/api/reports/purchases/export/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )