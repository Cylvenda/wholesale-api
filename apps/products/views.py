from django.db import transaction
from django.db.models import ProtectedError
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ModelViewSet
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


class CategoryViewSet(ModelViewSet):
    queryset = Category.objects.all().order_by("-created_at")
    serializer_class = CategorySerializer
    lookup_field = "uuid"
    lookup_url_kwarg = "uuid"
    permission_classes = [IsAuthenticated]


class BrandViewSet(ModelViewSet):
    queryset = Brand.objects.all().order_by("-created_at")
    serializer_class = BrandSerializer
    lookup_field = "uuid"
    lookup_url_kwarg = "uuid"
    permission_classes = [IsAuthenticated]


class UnitViewSet(ModelViewSet):
    queryset = Unit.objects.all().order_by("-created_at")
    serializer_class = UnitSerializer
    lookup_field = "uuid"
    lookup_url_kwarg = "uuid"
    permission_classes = [IsAuthenticated]

    def perform_destroy(self, instance):
        """Units referenced by products or history are deactivated, never deleted."""
        try:
            instance.delete()
        except ProtectedError as exc:
            raise ValidationError(
                {
                    "detail": "This unit is already in use by products or past transactions. "
                    "Deactivate it instead."
                }
            ) from exc


class ProductUnitViewSet(ModelViewSet):
    serializer_class = ProductUnitSerializer
    lookup_field = "uuid"
    lookup_url_kwarg = "uuid"
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        product_uuid = self.kwargs.get("product_uuid")
        if product_uuid:
            return ProductUnit.objects.filter(product__uuid=product_uuid).order_by("conversion_factor")
        return ProductUnit.objects.all().order_by("conversion_factor")


class ProductViewSet(ModelViewSet):
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