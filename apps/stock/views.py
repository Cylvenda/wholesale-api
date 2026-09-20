from django.db import transaction
from django.db.models import Sum
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet

from .models import Stock, StockMovement
from .serializers import StockMovementSerializer, StockSerializer
from .services import add_stock, remove_stock
from ..products.models import Product


# Movement types that increase stock.
INCREASE_TYPES = {
    StockMovement.MovementTypes.INITIAL,
    StockMovement.MovementTypes.PURCHASES,
    StockMovement.MovementTypes.RETURN,
    StockMovement.MovementTypes.STOCKTAKE_SURPLUS,
    StockMovement.MovementTypes.CANCEL,
    StockMovement.MovementTypes.PURCHASE_ADJUSTMENT,
}

# Movement types that decrease stock.
DECREASE_TYPES = {
    StockMovement.MovementTypes.SALES,
    StockMovement.MovementTypes.DAMAGES,
    StockMovement.MovementTypes.SALES_ADJUSTMENT,
    StockMovement.MovementTypes.STOCKTAKE_LOSS,
}


class StockViewSet(ReadOnlyModelViewSet):
    queryset = Stock.objects.select_related("product").order_by("-product__name")
    serializer_class = StockSerializer
    lookup_field = "uuid"
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=["get"])
    def summary(self, request):
        stocks = Stock.objects.select_related("product")

        stocked_products = stocks.filter(quantity__gt=0).count()
        total_quantity = (
            stocks.aggregate(total=Sum("quantity"))["total"] or 0
        )
        low_stock_items = stocks.filter(
            quantity__gt=0, quantity__lt=10
        ).count()
        out_of_stock_items = stocks.filter(quantity=0).count()

        stock_value = 0
        for stock in stocks:
            stock_value += float(stock.quantity) * float(
                stock.product.buying_price
            )

        return Response({
            "stocked_products": stocked_products,
            "total_quantity": total_quantity,
            "low_stock_items": low_stock_items,
            "out_of_stock_items": out_of_stock_items,
            "stock_value": stock_value,
        })


class StockMovementViewSet(ModelViewSet):
    queryset = StockMovement.objects.select_related(
        "stock", "stock__product"
    ).order_by("-created_at")
    serializer_class = StockMovementSerializer
    lookup_field = "uuid"
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def perform_create(self, serializer):
        product = serializer.validated_data.pop("product", None)
        movement_type = serializer.validated_data["movement_type"]
        quantity = serializer.validated_data["quantity"]
        reference = serializer.validated_data.get("reference", "")
        notes = serializer.validated_data.get("notes", "")
        user = self.request.user

        if product is None:
            raise ValidationError(
                {"product": "This field is required when creating a movement."}
            )

        if movement_type in INCREASE_TYPES:
            add_stock(
                product=product,
                quantity=quantity,
                movement_type=movement_type,
                reference=reference,
                note=notes,
                user=user,
            )
        elif movement_type in DECREASE_TYPES:
            remove_stock(
                product=product,
                quantity=quantity,
                movement_type=movement_type,
                reference=reference,
                note=notes,
                user=user,
            )
        else:
            raise ValidationError(
                {"movement_type": "This movement type cannot be applied manually."}
            )

    def perform_update(self, serializer):
        raise ValidationError(
            "Stock movements cannot be modified."
        )

    def perform_destroy(self, instance):
        raise ValidationError(
            "Stock movements cannot be deleted."
        )
