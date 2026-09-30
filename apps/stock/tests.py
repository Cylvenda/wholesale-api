from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.products.models import Brand, Category, Product, Unit
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
        brand = Brand.objects.create(
            name="Fanta Brand", category=category, created_by=self.user
        )
        unit = Unit.objects.create(name="Case", created_by=self.user)
        self.product = Product.objects.create(
            brand=brand,
            unit=unit,
            name="Fanta",
            buying_price=Decimal("1000.00"),
            selling_price=Decimal("1500.00"),
            created_by=self.user,
        )
        Stock.objects.create(product=self.product, quantity=3, created_by=self.user)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_decrease_above_available_stock_returns_quantity_error(self):
        response = self.client.post(
            "/api/stock-movements/",
            {
                "product": str(self.product.uuid),
                "movement_type": "Stocktake Loss",
                "quantity": 5,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn(
            "Insufficient stock for Fanta.", response.data["data"]["quantity"]
        )
        self.assertEqual(Stock.objects.get(product=self.product).quantity, 3)
