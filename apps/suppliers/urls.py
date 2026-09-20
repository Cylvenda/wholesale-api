from rest_framework.routers import DefaultRouter

from apps.payments.views import PaymentViewSet
from apps.suppliers.views import SupplierViewSet

router = DefaultRouter()

router.register("suppliers", SupplierViewSet, basename="supplier")

urlpatterns = router.urls