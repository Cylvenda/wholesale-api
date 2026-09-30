from decimal import Decimal
from django.db import transaction
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from .models import Purchase, PurchaseItem
from .serializers import PurchaseSerializer
from config.reference_codes import format_reference
from ..stock.models import StockMovement
from ..stock.services import add_stock, remove_stock


class PurchaseViewSet(viewsets.ModelViewSet):
    queryset = (
        Purchase.objects.prefetch_related("items")
        .select_related("supplier")
        .order_by("-created_at")
    )
    serializer_class = PurchaseSerializer
    lookup_field = "uuid"
    lookup_url_kwarg = "uuid"

    @transaction.atomic
    def perform_create(self, serializer):
        validated_data = serializer.validated_data

        items_data = validated_data.pop("items", [])

        if self.request.user.is_authenticated:
            validated_data["created_by"] = self.request.user

        purchase = Purchase.objects.create(**validated_data)
        reference = format_reference("PUR", purchase.pk)

        total = Decimal("0.00")

        for item_data in items_data:
            quantity = item_data["quantity"]
            unit_cost = item_data["unit_cost"]
            product = item_data["product"]

            subtotal = quantity * unit_cost

            PurchaseItem.objects.create(
                purchase=purchase,
                product=product,
                quantity=quantity,
                unit_cost=unit_cost,
                subtotal=subtotal,
                created_by=self.request.user,
            )

            add_stock(
                product=product,
                quantity=quantity,
                movement_type=StockMovement.MovementTypes.PURCHASES,
                reference=reference,
                note=f"Purchase {reference}",
                user=self.request.user,
            )

            total += subtotal

        purchase.total = total
        purchase.status = Purchase.Status.COMPLETED

        purchase.save(update_fields=["total", "status"])

        serializer.instance = purchase
        return purchase

    @transaction.atomic
    def perform_update(self, serializer):
        purchase = serializer.instance

        if purchase.status != Purchase.Status.COMPLETED:
            raise ValidationError("Only completed purchases can be modified.")

        validated_data = serializer.validated_data

        # Get the new items from the validated data
        items_data = validated_data.pop("items", None)

        # Update normal Purchase fields
        for field, value in validated_data.items():
            setattr(purchase, field, value)

        purchase.save()

        # If items were not included in the request,
        # don't change the existing items/stock.
        if items_data is None:
            return

        # 1. Reverse old purchase items from stock

        old_items = list(purchase.items.select_related("product"))

        for item in old_items:
            remove_stock(
                product=item.product,
                quantity=item.quantity,
                movement_type=StockMovement.MovementTypes.PURCHASE_ADJUSTMENT,
                reference=format_reference("PUR", purchase.pk),
                note="Reversing previous purchase item",
                user=self.request.user,
            )

        # 2. Delete old purchase items

        purchase.items.all().delete()

        # 3. Create new purchase items
        #    and add their stock

        total = Decimal("0.00")

        for item_data in items_data:
            product = item_data["product"]
            quantity = item_data["quantity"]
            unit_cost = item_data["unit_cost"]

            subtotal = quantity * unit_cost

            PurchaseItem.objects.create(
                purchase=purchase,
                product=product,
                quantity=quantity,
                unit_cost=unit_cost,
                subtotal=subtotal,
                created_by=self.request.user,
            )

            add_stock(
                product=product,
                quantity=quantity,
                movement_type=StockMovement.MovementTypes.PURCHASE_ADJUSTMENT,
                reference=format_reference("PUR", purchase.pk),
                note=f"Purchase {format_reference('PUR', purchase.pk)} updated",
                user=self.request.user,
            )

            total += subtotal

        purchase.total = total
        purchase.status = Purchase.Status.COMPLETED

        purchase.save(update_fields=["total", "status"])

    @action(detail=True, methods=["post"], url_path="cancel")
    @transaction.atomic
    def cancel(self, request, uuid=None):
        purchase = self.get_object()

        if purchase.status == Purchase.Status.CANCELLED:
            raise ValidationError("This purchase has already been cancelled.")

        if purchase.status != Purchase.Status.COMPLETED:
            raise ValidationError("Only completed purchases can be cancelled.")

        user = request.user if request.user.is_authenticated else None

        for item in purchase.items.select_related("product"):
            remove_stock(
                product=item.product,
                quantity=item.quantity,
                movement_type=(StockMovement.MovementTypes.CANCEL),
                reference=format_reference("PUR", purchase.pk),
                note=f"Purchase {format_reference('PUR', purchase.pk)} cancelled",
                user=user,
            )

        purchase.status = Purchase.Status.CANCELLED
        purchase.save(update_fields=["status"])

        return Response(PurchaseSerializer(purchase, context={"request": request}).data)

    def perform_destroy(self, instance):
        raise ValidationError("Purchases are immutable. Use the cancel action instead.")
