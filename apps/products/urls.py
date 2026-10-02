from django.urls import path, include
from rest_framework.routers import DefaultRouter

from apps.products.views import CategoryViewSet, ProductViewSet, BrandViewSet, UnitViewSet, ProductUnitViewSet

router = DefaultRouter()

router.register("categories", CategoryViewSet, basename="category")
router.register("brands", BrandViewSet, basename="brand")
router.register("products", ProductViewSet, basename="product")
router.register("units", UnitViewSet, basename="unit")

urlpatterns = router.urls + [
    path(
        "products/<uuid:product_uuid>/units/",
        ProductUnitViewSet.as_view({"get": "list", "post": "create"}),
        name="product-units-list",
    ),
    path(
        "products/<uuid:product_uuid>/units/<uuid:uuid>/",
        ProductUnitViewSet.as_view({"get": "retrieve", "patch": "partial_update", "delete": "destroy"}),
        name="product-units-detail",
    ),
]