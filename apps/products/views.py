from django.db import transaction
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ModelViewSet

from config.destroy import SafeDestroyMixin
from .models import Category, Product, Brand, Unit, ProductUnit
from .serializers import (
    CategorySerializer,
    ProductSerializer,
    ProductCreateUpdateSerializer,
    BrandSerializer,
    UnitSerializer,
    ProductUnitSerializer,
)
from ..purchases.models import PurchaseItem
from ..sales.models import SaleItem
from ..stock.models import Stock, StockMovement


class CategoryViewSet(SafeDestroyMixin, ModelViewSet):
    queryset = Category.objects.all().order_by("-created_at")
    serializer_class = CategorySerializer
    lookup_field = "uuid"
    lookup_url_kwarg = "uuid"
    permission_classes = [IsAuthenticated]


class BrandViewSet(SafeDestroyMixin, ModelViewSet):
    queryset = Brand.objects.all().order_by("-created_at")
    serializer_class = BrandSerializer
    lookup_field = "uuid"
    lookup_url_kwarg = "uuid"
    permission_classes = [IsAuthenticated]


class UnitViewSet(SafeDestroyMixin, ModelViewSet):
    queryset = Unit.objects.all().order_by("-created_at")
    serializer_class = UnitSerializer
    lookup_field = "uuid"
    lookup_url_kwarg = "uuid"
    permission_classes = [IsAuthenticated]


class ProductUnitViewSet(SafeDestroyMixin, ModelViewSet):
    serializer_class = ProductUnitSerializer
    lookup_field = "uuid"
    lookup_url_kwarg = "uuid"
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        product_uuid = self.kwargs.get("product_uuid")
        if product_uuid:
            return ProductUnit.objects.filter(product__uuid=product_uuid).order_by("conversion_factor")
        return ProductUnit.objects.all().order_by("conversion_factor")


class ProductViewSet(SafeDestroyMixin, ModelViewSet):
    queryset = Product.objects.all().order_by("-created_at")
    serializer_class = ProductSerializer
    lookup_field = "uuid"
    lookup_url_kwarg = "uuid"
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action in ["create", "update", "partial_update"]:
            return ProductCreateUpdateSerializer
        return ProductSerializer

    @transaction.atomic
    def perform_create(self, serializer):
        product = serializer.save(created_by=self.request.user)
        Stock.objects.create(
            product=product,
            quantity=0,
            created_by=self.request.user,
        )

        StockMovement.objects.create(
            stock=product.stock,
            movement_type=StockMovement.MovementTypes.INITIAL,
            notes="Initial stock",
            created_by=self.request.user,
        )

    def destroy_instance(self, instance):
        """Delete the product, clearing its own stock row when that is safe.

        Creating a product always opens a ``Stock`` row plus an ``INITIAL``
        movement, and both are ``PROTECT``, so a plain delete could never
        succeed. A product that was never bought, sold or counted holds nothing
        worth keeping, so that scaffolding is dropped first. Anything with real
        history is reported with the reason instead.
        """
        stock = getattr(instance, "stock", None)
        if stock is not None and int(stock.quantity) == 0:
            has_history = (
                instance.sale_items.exists()
                or instance.purchase_items.exists()
                or stock.movements.exclude(
                    movement_type=StockMovement.MovementTypes.INITIAL
                ).exists()
            )
            if not has_history:
                stock.movements.all().delete()
                stock.delete()
                instance.delete()
                return

        if stock is not None:
            blockers = []
            if int(stock.quantity) > 0:
                blockers.append(f"{int(stock.quantity)} units still on hand")
            if instance.sale_items.exists():
                blockers.append("recorded sales")
            if instance.purchase_items.exists():
                blockers.append("recorded purchases")
            if blockers:
                raise ValidationError(
                    "This product cannot be deleted because it has "
                    f"{', '.join(blockers)}. Set it to inactive instead so its "
                    "history stays intact."
                )

        instance.delete()

    @transaction.atomic
    def perform_update(self, serializer):
        product = serializer.instance
        old_base_unit = product.base_unit
        new_base_unit = serializer.validated_data.get("base_unit", old_base_unit)

        if new_base_unit.pk != old_base_unit.pk:
            raise ValidationError(
                {"base_unit": "Changing the base unit is not supported. Create a new product instead."}
            )

        serializer.save()