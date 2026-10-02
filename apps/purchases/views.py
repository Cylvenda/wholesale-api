from django.db import transaction
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from .models import Purchase, PurchaseItem
from .serializers import PurchaseSerializer, PurchaseCreateUpdateSerializer
from config.reference_codes import format_reference
from ..stock.models import StockMovement
from ..stock.services import add_stock, remove_stock


class PurchaseViewSet(viewsets.ModelViewSet):
    queryset = (
        Purchase.objects.prefetch_related("items__product", "items__product_unit__unit")
        .select_related("supplier")
        .order_by("-created_at")
    )
    serializer_class = PurchaseSerializer
    lookup_field = "uuid"
    lookup_url_kwarg = "uuid"

    def get_serializer_class(self):
        if self.action in ["create", "update", "partial_update"]:
            return PurchaseCreateUpdateSerializer
        return PurchaseSerializer

    @action(detail=True, methods=["post"], url_path="cancel")
    @transaction.atomic
    def cancel(self, request, uuid=None):
        purchase = self.get_object()

        if purchase.status == Purchase.Status.CANCELLED:
            raise ValidationError("This purchase has already been cancelled.")

        if purchase.status != Purchase.Status.COMPLETED:
            raise ValidationError("Only completed purchases can be cancelled.")

        user = request.user if request.user.is_authenticated else None

        for item in purchase.items.select_related("product", "product_unit__unit"):
            remove_stock(
                product=item.product,
                base_quantity=item.base_quantity,
                movement_type=StockMovement.MovementTypes.CANCEL,
                reference=format_reference("PUR", purchase.pk),
                note=f"Purchase {format_reference('PUR', purchase.pk)} cancelled",
                user=user,
            )

        purchase.status = Purchase.Status.CANCELLED
        purchase.save(update_fields=["status"])

        return Response(PurchaseSerializer(purchase, context={"request": request}).data)

    def perform_destroy(self, instance):
        raise ValidationError("Purchases are immutable. Use the cancel action instead.")