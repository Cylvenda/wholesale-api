from decimal import Decimal

from django.db.models import Sum

from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from config.destroy import SafeDestroyMixin
from config.money import to_money
from .models import Customer
from .serializers import CustomerSerializer

from apps.sales.models import Sale


class CustomerViewSet(SafeDestroyMixin, ModelViewSet):
    queryset = Customer.objects.all().order_by("-created_at")
    serializer_class = CustomerSerializer
    lookup_field = "uuid"
    lookup_url_kwarg = "uuid"
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=["get"])
    def summary(self, request):
        customers = Customer.objects.all()

        total_customers = customers.count()
        active_customers = customers.filter(is_active=True).count()

        completed_sales = Sale.objects.filter(
            customer__in=customers,
            status=Sale.Status.COMPLETED,
        )

        total_sales = to_money(
            completed_sales.aggregate(total=Sum("total"))["total"]
        )

        unpaid_sales = completed_sales.filter(
            payment_status=Sale.PaymentStatus.UNPAID,
        )

        partial_sales = completed_sales.filter(
            payment_status=Sale.PaymentStatus.PARTIAL,
        )

        # Money is summed as Decimal so the customer balance matches the sale
        # and payment rows exactly, like the receipts and reports do.
        outstanding = Decimal("0.00")

        for sale in unpaid_sales:
            outstanding += to_money(sale.total)

        for sale in partial_sales:
            paid = to_money(
                sale.payments.aggregate(total=Sum("amount"))["total"]
            )
            outstanding += to_money(sale.total) - paid

        return Response({
            "total_customers": total_customers,
            "active_customers": active_customers,
            "total_sales": str(total_sales),
            "outstanding": str(outstanding),
        })
