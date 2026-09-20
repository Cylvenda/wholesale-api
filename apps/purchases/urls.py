from rest_framework.routers import DefaultRouter
from apps.purchases.views import PurchaseViewSet

router = DefaultRouter()

router.register("purchases", PurchaseViewSet, basename="purchase")

urlpatterns = router.urls