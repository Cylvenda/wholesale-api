from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.customers.models import Customer
from apps.sales.models import Sale
from .models import Payment
from .serializers import PaymentSerializer
from .services import update_sale_payment_status


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
        serializer = PaymentSerializer(
            data={
                "sale": str(self.sale.uuid),
                "amount": "-1.00",
                "method": "cash",
                "payment_date": timezone.now(),
            }
        )

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
        self.assertEqual(response.data["reference_code"], f"PAY-{payment.pk:06d}")
        payment.refresh_from_db()
        self.sale.refresh_from_db()
        self.assertEqual(payment.amount, Decimal("100.00"))
        self.assertEqual(self.sale.payment_status, Sale.PaymentStatus.PAID)

    def test_payment_reference_is_generated_not_accepted_from_the_client(self):
        client = APIClient()
        client.force_authenticate(self.user)

        response = client.post(
            "/api/payments/",
            {
                "sale": str(self.sale.uuid),
                "amount": "40.00",
                "method": "cash",
                "reference": "TYPED-BY-USER",
                "payment_date": timezone.now().isoformat(),
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        payment = Payment.objects.get()
        self.assertEqual(payment.reference, f"PAY-{payment.pk:06d}")
        self.assertNotEqual(payment.reference, "TYPED-BY-USER")
        self.assertEqual(response.data["reference"], f"PAY-{payment.pk:06d}")

    def test_payment_reports_the_exact_money_of_its_sale(self):
        """Amount, amount paid and balance must match the sale exactly."""
        self.sale.total = Decimal("1100.50")
        self.sale.save(update_fields=["total"])

        client = APIClient()
        client.force_authenticate(self.user)

        response = client.post(
            "/api/payments/",
            {
                "sale": str(self.sale.uuid),
                "amount": "400.25",
                "method": "cash",
                "payment_date": timezone.now().isoformat(),
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["amount"], "400.25")
        self.assertEqual(response.data["sale_total"], "1100.50")
        self.assertEqual(response.data["amount_paid"], "400.25")
        self.assertEqual(response.data["outstanding_balance"], "700.25")

    def test_balance_is_never_reported_as_negative(self):
        self.sale.total = Decimal("50.00")
        self.sale.save(update_fields=["total"])
        Payment.objects.create(
            customer=self.customer,
            sale=self.sale,
            amount=Decimal("50.00"),
            method="cash",
            payment_date=timezone.now(),
            created_by=self.user,
        )

        serializer = PaymentSerializer(Payment.objects.latest("created_at"))

        self.assertEqual(serializer.data["outstanding_balance"], "0.00")

    def test_summary_outstanding_keeps_decimal_precision(self):
        """A float sum would show 0.3 - 0.1 style drift on the summary."""
        self.sale.total = Decimal("0.30")
        self.sale.save(update_fields=["total"])
        Payment.objects.create(
            customer=self.customer,
            sale=self.sale,
            amount=Decimal("0.10"),
            method="cash",
            payment_date=timezone.now(),
            created_by=self.user,
        )
        update_sale_payment_status(self.sale)

        client = APIClient()
        client.force_authenticate(self.user)
        summary = client.get("/api/payments/summary/").data

        self.assertEqual(summary["outstanding"], "0.20")
        self.assertEqual(summary["total_paid"], "0.10")
