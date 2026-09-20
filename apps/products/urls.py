from rest_framework.routers import DefaultRouter

from apps.products.views import CategoryViewSet, ProductViewSet, BrandViewSet, UnitViewSet

router = DefaultRouter()

router.register("categories", CategoryViewSet, basename="category")
router.register("brands", BrandViewSet, basename="brand")
router.register("products", ProductViewSet, basename="product")
router.register("units", UnitViewSet, basename="unit")

urlpatterns = router.urls