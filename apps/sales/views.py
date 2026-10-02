from django.db import transaction
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet
from .models import Sale, SaleItem
from .serializers import SaleSerializer, SaleCreateUpdateSerializer
from config.reference_codes import format_reference
from ..stock.models import Stock, StockMovement
from ..stock.services import remove_stock, add_stock


class SaleViewSet(ModelViewSet):
    queryset = (
        Sale.objects.prefetch_related("items__product", "items__product_unit__unit")
        .select_related("customer")
        .order_by("-created_at")
    )
    serializer_class = SaleSerializer
    lookup_field = "uuid"
    lookup_url_kwarg = "uuid"

    def get_serializer_class(self):
        if self.action in ["create", "update", "partial_update"]:
            return SaleCreateUpdateSerializer
        return SaleSerializer

    @action(detail=True, methods=["post"], url_path="cancel")
    @transaction.atomic
    def cancel(self, request, uuid=None):
        sale = self.get_object()

        if sale.status == Sale.Status.CANCELLED:
            raise ValidationError("This sale has already been cancelled.")

        if sale.status != Sale.Status.COMPLETED:
            raise ValidationError("Only completed sales can be cancelled.")

        user = request.user if request.user.is_authenticated else None

        # Return sold products to stock
        for item in sale.items.select_related("product", "product_unit__unit"):
            add_stock(
                product=item.product,
                base_quantity=item.base_quantity,
                movement_type=(StockMovement.MovementTypes.CANCEL),
                reference=format_reference("SAL", sale.pk),
                note=f"Sale {format_reference('SAL', sale.pk)} cancelled",
                user=user,
            )

        sale.status = Sale.Status.CANCELLED
        sale.save(update_fields=["status"])

        return Response(
            SaleSerializer(sale, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )

    def perform_destroy(self, instance):
        raise ValidationError("Sales are immutable. Use the cancel action instead.")