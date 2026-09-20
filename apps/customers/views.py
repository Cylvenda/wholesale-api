from django.db.models import Sum

from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from .models import Customer
from .serializers import CustomerSerializer

from apps.sales.models import Sale


class CustomerViewSet(ModelViewSet):
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

        total_sales = (
            completed_sales.aggregate(total=Sum("total"))["total"]
            or 0
        )

        unpaid_sales = completed_sales.filter(
            payment_status=Sale.PaymentStatus.UNPAID,
        )

        partial_sales = completed_sales.filter(
            payment_status=Sale.PaymentStatus.PARTIAL,
        )

        outstanding = 0

        for sale in unpaid_sales:
            outstanding += float(sale.total)

        for sale in partial_sales:
            paid = (
                sale.payments.aggregate(total=Sum("amount"))["total"]
                or 0
            )
            outstanding += float(sale.total) - float(paid)

        return Response({
            "total_customers": total_customers,
            "active_customers": active_customers,
            "total_sales": total_sales,
            "outstanding": outstanding,
        })
