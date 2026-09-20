from rest_framework.routers import DefaultRouter
from apps.stock.views import StockMovementViewSet, StockViewSet

router = DefaultRouter()

router.register("stocks", StockViewSet, basename="stock")
router.register("stock-movements", StockMovementViewSet, basename="stock-movement")

urlpatterns = router.urls
