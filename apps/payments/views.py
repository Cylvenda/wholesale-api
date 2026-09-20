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

        today_payments = (
            Payment.objects
            .filter(payment_date__date=today)
            .aggregate(total=Sum("amount"))["total"]
            or 0
        )

        total_paid = (
            Payment.objects
            .aggregate(total=Sum("amount"))["total"]
            or 0
        )

        completed_sales = Sale.objects.filter(
            status=Sale.Status.COMPLETED
        )

        paid_amounts = completed_sales.annotate(
            paid=Sum("payments__amount")
        )

        outstanding = 0
        pending_count = 0

        for sale in paid_amounts:
            paid = sale.paid or 0
            if sale.payment_status == Sale.PaymentStatus.UNPAID:
                outstanding += float(sale.total) - float(paid)
                pending_count += 1
            elif sale.payment_status == Sale.PaymentStatus.PARTIAL:
                outstanding += float(sale.total) - float(paid)

        return Response({
            "today_payments": today_payments,
            "total_paid": total_paid,
            "outstanding": outstanding,
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

        paid_amount = (
            sale.payments.aggregate(
                total=Sum("amount")
            )["total"]
            or 0
        )

        outstanding = sale.total - paid_amount

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

        other_paid = (
                sale.payments
                .exclude(pk=payment.pk)
                .aggregate(
                    total=Sum("amount")
                )["total"]
                or 0
        )

        outstanding = sale.total - other_paid

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
