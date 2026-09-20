from rest_framework.routers import DefaultRouter

from apps.sales.views import SaleViewSet

router = DefaultRouter()

router.register("sales", SaleViewSet, basename="sale")

urlpatterns = router.urls