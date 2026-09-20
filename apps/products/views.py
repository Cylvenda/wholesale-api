from django.db import transaction
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ModelViewSet
from .models import Category, Product, Brand, Unit
from .serializers import CategorySerializer, ProductSerializer, BrandSerializer, UnitSerializer
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

class ProductViewSet(ModelViewSet):
    queryset = Product.objects.all().order_by("-created_at")
    serializer_class = ProductSerializer
    lookup_field = "uuid"
    lookup_url_kwarg = "uuid"
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def perform_create(self, serializer):

        product = serializer.save(
            created_by=self.request.user
        )
        stock = Stock.objects.create(
            product=product,
            created_by=self.request.user,
        )

        StockMovement.objects.create(
            stock=stock,
            movement_type=StockMovement.MovementTypes.INITIAL,
            notes="Initial stock",
            created_by=self.request.user,
        )