from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .models import Stock, StockMovement
from .serializers import (
    StockAdjustmentSerializer,
    StockMovementSerializer,
    StockSerializer,
    UnitAvailabilitySerializer,
)
from config.reference_codes import format_reference
from .services import (
    add_stock,
    availability,
    convert_to_base_quantity,
    remove_stock,
    stock_value,
)
from ..products.models import Product, ProductUnit


class StockViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = (
        Stock.objects.select_related("product", "product__base_unit")
        .order_by("product__name")
    )
    serializer_class = StockSerializer
    lookup_field = "uuid"
    lookup_url_kwarg = "uuid"
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=["get"], url_path="summary")
    def summary(self, request):
        stocks = self.get_queryset().select_related("product__base_unit")
        stocked_products = stocks.exclude(quantity=0).count()
        total_quantity = sum(int(s.quantity) for s in stocks)
        low_stock_items = stocks.filter(quantity__gt=0, quantity__lt=10).count()
        out_of_stock_items = stocks.filter(quantity=0).count()
        # Stock is counted in base units, so it is valued with the base unit's
        # own configured buying price rather than any pack price.
        stock_value_total = stock_value(stocks)

        return Response({
            "stocked_products": stocked_products,
            "total_quantity": total_quantity,
            "low_stock_items": low_stock_items,
            "out_of_stock_items": out_of_stock_items,
            "stock_value": str(stock_value_total),
        })

    @action(detail=False, methods=["get"], url_path="availability")
    def availability(self, request):
        """Stock expressed in the selected selling unit.

        ``GET /api/stocks/availability/?product=<uuid>&unit=<uuid>``

        Without ``unit`` every active unit configured for the product is
        returned, so the client always renders the same numbers the backend
        validates against.
        """
        product_uuid = request.query_params.get("product")
        unit_uuid = request.query_params.get("unit")

        if not product_uuid:
            raise ValidationError({"product": "This query parameter is required."})

        try:
            product = Product.objects.select_related("base_unit").get(uuid=product_uuid)
        except (Product.DoesNotExist, ValueError, TypeError) as exc:
            raise ValidationError({"product": "Product not found."}) from exc

        if not product.is_active:
            raise ValidationError({"product": f"{product.name} is not an active product."})

        product_units = list(
            ProductUnit.objects.filter(product=product, is_active=True)
            .select_related("unit")
            .order_by("conversion_factor")
        )

        if unit_uuid:
            selected = next((pu for pu in product_units if str(pu.uuid) == unit_uuid), None)
            if selected is None:
                raise ValidationError(
                    {"unit": "Selected unit is not configured for this product."}
                )
            product_units = [selected]

        payload = [availability(product, pu) for pu in product_units]
        serializer = UnitAvailabilitySerializer(payload, many=True)
        return Response(serializer.data)


class StockMovementViewSet(viewsets.ModelViewSet):
    queryset = (
        StockMovement.objects.select_related("stock__product", "transaction_unit", "base_unit")
        .order_by("-created_at")
    )
    serializer_class = StockMovementSerializer
    lookup_field = "uuid"
    lookup_url_kwarg = "uuid"
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "head", "options"]

    def create(self, request, *args, **kwargs):
        """Stocktake adjustments are created through the adjust serializer."""
        return self.adjust(request)

    @action(detail=False, methods=["post"], url_path="adjust")
    def adjust(self, request):
        serializer = StockAdjustmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        product = data["product"]
        product_unit = data["product_unit"]
        movement_type = data["movement_type"]
        quantity = data["quantity"]
        notes = data.get("notes", "")
        user = request.user if request.user.is_authenticated else None

        # The user counted whole units of the selected unit; inventory always
        # moves in base units, so convert here using the ProductUnit's own factor.
        base_quantity = convert_to_base_quantity(product_unit, quantity)
        unit_kwargs = {
            "transaction_unit": product_unit.unit,
            "transaction_quantity": quantity,
            "conversion_factor_used": product_unit.conversion_factor,
        }

        if movement_type == StockMovement.MovementTypes.STOCKTAKE_SURPLUS:
            try:
                stock, movement = add_stock(
                    product=product,
                    base_quantity=base_quantity,
                    movement_type=movement_type,
                    reference="",
                    note=notes,
                    user=user,
                    **unit_kwargs,
                )
            except ValueError as exc:
                raise ValidationError({"quantity": str(exc)}) from exc
        elif movement_type == StockMovement.MovementTypes.STOCKTAKE_LOSS:
            try:
                stock, movement = remove_stock(
                    product=product,
                    base_quantity=base_quantity,
                    movement_type=movement_type,
                    reference="",
                    note=notes,
                    user=user,
                    **unit_kwargs,
                )
            except ValueError as exc:
                raise ValidationError({"quantity": str(exc)}) from exc
        else:
            raise ValidationError("Invalid movement type for adjustment.")

        # Stocktakes have no document to reference, so the movement gets the
        # same automatic code every other transaction carries.
        if not movement.reference:
            movement.reference = format_reference("ADJ", movement.pk)
            movement.save(update_fields=["reference"])

        return Response(
            StockMovementSerializer(movement, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )