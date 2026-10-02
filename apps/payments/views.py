from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from .models import Payment
from .serializers import PaymentSerializer
from config.money import to_money
from .services import update_sale_payment_status

from apps.sales.models import Sale


class PaymentViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated]
    queryset = (
        Payment.objects
        .select_related("customer", "sale")
        .order_by("-created_at")
    )

    serializer_class = PaymentSerializer
    lookup_field = "uuid"

    @action(detail=False, methods=["get"])
    def summary(self, request):
        today = timezone.now().date()

        today_payments = to_money(
            Payment.objects
            .filter(payment_date__date=today)
            .aggregate(total=Sum("amount"))["total"]
        )

        total_paid = to_money(
            Payment.objects.aggregate(total=Sum("amount"))["total"]
        )

        completed_sales = Sale.objects.filter(
            status=Sale.Status.COMPLETED
        )

        paid_amounts = completed_sales.annotate(
            paid=Sum("payments__amount")
        )

        # Money is summed as Decimal: floats would drift away from the exact
        # amounts recorded on the sale and its payments.
        outstanding = Decimal("0.00")
        pending_count = 0

        for sale in paid_amounts:
            paid = to_money(sale.paid)
            if sale.payment_status == Sale.PaymentStatus.UNPAID:
                outstanding += to_money(sale.total) - paid
                pending_count += 1
            elif sale.payment_status == Sale.PaymentStatus.PARTIAL:
                outstanding += to_money(sale.total) - paid

        return Response({
            "today_payments": str(today_payments),
            "total_paid": str(total_paid),
            "outstanding": str(outstanding),
            "pending": pending_count,
        })

    @transaction.atomic
    def perform_create(self, serializer):

        sale = (
            Sale.objects
            .select_for_update()
            .get(
                uuid=serializer.validated_data["sale"].uuid
            )
        )

        if sale.status != Sale.Status.COMPLETED:
            raise serializers.ValidationError(
                "Payment can only be made for a completed sale."
            )

        amount = serializer.validated_data["amount"]

        paid_amount = to_money(
            sale.payments.aggregate(total=Sum("amount"))["total"]
        )

        outstanding = to_money(sale.total) - paid_amount

        if outstanding <= 0:
            raise serializers.ValidationError(
                "This sale has already been fully paid."
            )

        if amount > outstanding:
            raise serializers.ValidationError({
                "amount": (
                    f"Maximum payment allowed is "
                    f"{outstanding}."
                )
            })

        user = (
            self.request.user
            if self.request.user.is_authenticated
            else None
        )

        serializer.save(
            customer=sale.customer,
            created_by=user,
        )

        update_sale_payment_status(sale)

    @transaction.atomic
    def perform_update(self, serializer):

        payment = self.get_object()

        sale = (
            Sale.objects
            .select_for_update()
            .get(pk=payment.sale_id)
        )

        if sale.status != Sale.Status.COMPLETED:
            raise serializers.ValidationError(
                "Payments can only be modified for completed sales."
            )

        new_amount = serializer.validated_data.get(
            "amount",
            payment.amount
        )

        other_paid = to_money(
            sale.payments
            .exclude(pk=payment.pk)
            .aggregate(total=Sum("amount"))["total"]
        )

        outstanding = to_money(sale.total) - other_paid

        if new_amount > outstanding:
            raise serializers.ValidationError({
                "amount": (
                    f"Maximum payment allowed is "
                    f"{outstanding}."
                )
            }
            )

        serializer.save(sale=sale, customer=sale.customer)
        update_sale_payment_status(sale)

    @transaction.atomic
    def perform_destroy(self, instance):

        sale = (
            Sale.objects
            .select_for_update()
            .get(pk=instance.sale_id)
        )

        if sale.status != Sale.Status.COMPLETED:
            raise serializers.ValidationError(
                "Payments can only be deleted for completed sales."
            )

        instance.delete()
        update_sale_payment_status(sale)
