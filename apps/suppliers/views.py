from django.db.models import Sum

from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from .models import Supplier
from .serializers import SupplierSerializer

from apps.purchases.models import Purchase


class SupplierViewSet(ModelViewSet):
    queryset = Supplier.objects.all().order_by("-created_at")
    serializer_class = SupplierSerializer
    lookup_field = "uuid"
    lookup_url_kwarg = "uuid"
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=["get"])
    def summary(self, request):
        suppliers = Supplier.objects.all()

        total_suppliers = suppliers.count()
        active_suppliers = suppliers.filter(is_active=True).count()

        completed_purchases = Purchase.objects.filter(
            supplier__in=suppliers,
            status=Purchase.Status.COMPLETED,
        )

        total_purchases = (
            completed_purchases.aggregate(total=Sum("total"))["total"]
            or 0
        )

        return Response({
            "total_suppliers": total_suppliers,
            "active_suppliers": active_suppliers,
            "total_purchases": total_purchases,
        })
