from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.customers.models import Customer
from apps.sales.models import Sale
from .models import Payment
from .serializers import PaymentSerializer


class PaymentAPITests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="cashier@example.com",
            phone="255700000001",
            password="safe-password-123",
            role=User.Roles.ACCOUNTANT,
        )
        self.customer = Customer.objects.create(name="Acme", created_by=self.user)
        self.sale = Sale.objects.create(
            customer=self.customer,
            status=Sale.Status.COMPLETED,
            total=Decimal("100.00"),
            sale_date=timezone.now(),
            created_by=self.user,
        )

    def test_payment_amount_must_be_positive(self):
        serializer = PaymentSerializer(data={
            "sale": str(self.sale.uuid),
            "amount": "-1.00",
            "method": "cash",
            "payment_date": timezone.now(),
        })

        self.assertFalse(serializer.is_valid())
        self.assertIn("amount", serializer.errors)

    def test_payment_update_is_persisted_and_recalculates_status(self):
        payment = Payment.objects.create(
            customer=self.customer,
            sale=self.sale,
            amount=Decimal("25.00"),
            method="cash",
            payment_date=timezone.now(),
            created_by=self.user,
        )
        client = APIClient()
        client.force_authenticate(self.user)

        response = client.patch(
            f"/api/payments/{payment.uuid}/",
            {"amount": "100.00"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        payment.refresh_from_db()
        self.sale.refresh_from_db()
        self.assertEqual(payment.amount, Decimal("100.00"))
        self.assertEqual(self.sale.payment_status, Sale.PaymentStatus.PAID)
