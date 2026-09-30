from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.products.models import Product, Category, Brand, Unit
from apps.stock.models import Stock
from apps.stock.services import add_stock
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
        self.unit = Unit.objects.create(
            name="Bottle", abbreviation="BTL", created_by=self.user
        )
        self.product = Product.objects.create(
            brand=self.brand,
            unit=self.unit,
            name="Safari Lager 500ml",
            buying_price=Decimal("1000.00"),
            selling_price=Decimal("1500.00"),
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

    def test_create_purchase_increases_stock_and_calculates_total(self):
        response = self.client.post(
            "/api/purchases/",
            {
                "supplier": str(self.supplier.uuid),
                "invoice_number": "PUR-001",
                "purchase_date": timezone.now().isoformat(),
                "notes": "",
                "items": [
                    {
                        "product": str(self.product.uuid),
                        "quantity": 10,
                        "unit_cost": "1000.00",
                    }
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        purchase = Purchase.objects.get()
        self.assertEqual(purchase.total, Decimal("10000.00"))
        self.assertEqual(purchase.status, Purchase.Status.COMPLETED)
        reference_code = f"PUR-{purchase.pk:06d}"
        self.assertEqual(response.data["reference_code"], reference_code)

        stock = Stock.objects.get(product=self.product)
        self.assertEqual(stock.quantity, 10)

        movement = self.client.get("/api/stock-movements/").data["results"][0]
        self.assertEqual(movement["reference"], reference_code)
        self.assertEqual(movement["unit_name"], "Bottle (BTL)")
        self.assertNotIn(str(purchase.uuid), movement["notes"])

        stock_data = self.client.get("/api/stocks/").data["results"][0]
        self.assertEqual(stock_data["unit_name"], "Bottle (BTL)")

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

    def test_cancel_reverses_stock(self):
        from apps.stock.models import StockMovement

        add_stock(
            product=self.product,
            quantity=5,
            movement_type=StockMovement.MovementTypes.PURCHASES,
            reference="initial",
            note="Initial test stock",
            user=self.user,
        )

        purchase = Purchase.objects.create(
            supplier=self.supplier,
            total=Decimal("10000.00"),
            purchase_date=timezone.now(),
            status=Purchase.Status.COMPLETED,
            created_by=self.user,
        )

        PurchaseItem.objects.create(
            purchase=purchase,
            product=self.product,
            quantity=5,
            unit_cost=Decimal("2000.00"),
            subtotal=Decimal("10000.00"),
            created_by=self.user,
        )

        response = self.client.post(f"/api/purchases/{purchase.uuid}/cancel/")

        self.assertEqual(response.status_code, 200)
        stock = Stock.objects.get(product=self.product)
        self.assertEqual(stock.quantity, 0)
        purchase.refresh_from_db()
        self.assertEqual(purchase.status, Purchase.Status.CANCELLED)
