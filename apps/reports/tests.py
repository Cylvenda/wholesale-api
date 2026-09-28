from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.customers.models import Customer
from apps.products.models import Brand, Category, Product, Unit
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
        brand = Brand.objects.create(
            name="Sample", category=category, created_by=self.user
        )
        unit = Unit.objects.create(
            name="Piece", abbreviation="PC", created_by=self.user
        )
        self.product = Product.objects.create(
            brand=brand,
            unit=unit,
            name="Long Product Name That Still Wraps Normally",
            buying_price=Decimal("8.00"),
            selling_price=Decimal("10.00"),
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

    def test_completed_sale_receipt_uses_sequential_number_and_bill_discount(self):
        sale = Sale.objects.create(
            customer=self.customer,
            sale_date=timezone.now(),
            subtotal=Decimal("20.00"),
            discount=Decimal("2.00"),
            total=Decimal("18.00"),
            status=Sale.Status.COMPLETED,
            created_by=self.user,
        )
        SaleItem.objects.create(
            sale=sale,
            product=self.product,
            quantity=2,
            unit_price=Decimal("10.00"),
            subtotal=Decimal("20.00"),
            created_by=self.user,
        )

        response = self.client.get(f"/api/sales/{sale.uuid}/receipt/?format=json")

        self.assertEqual(response.status_code, 200)
        receipt = response.data["data"]
        self.assertEqual(receipt["sale"]["receipt_number"], f"SAL-{sale.pk:06d}")
        self.assertEqual(receipt["items"][0]["unit"], "PC")
        self.assertNotIn("discount", receipt["items"][0])
        self.assertEqual(receipt["items"][0]["line_total"], Decimal("20.00"))
        self.assertEqual(receipt["totals"]["discount"], Decimal("2.00"))

    def test_completed_purchase_receipt_contains_received_goods(self):
        purchase = Purchase.objects.create(
            supplier=self.supplier,
            invoice_number="SUP-INV-17",
            purchase_date=timezone.now(),
            total=Decimal("16.00"),
            status=Purchase.Status.COMPLETED,
            created_by=self.user,
        )
        PurchaseItem.objects.create(
            purchase=purchase,
            product=self.product,
            quantity=2,
            unit_cost=Decimal("8.00"),
            subtotal=Decimal("16.00"),
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
        self.assertEqual(receipt["items"][0]["line_total"], Decimal("16.00"))
        self.assertEqual(receipt["totals"]["grand_total"], Decimal("16.00"))
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
