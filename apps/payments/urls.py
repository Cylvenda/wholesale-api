from rest_framework.routers import DefaultRouter

from apps.payments.views import PaymentViewSet

router = DefaultRouter()

router.register("payments", PaymentViewSet, basename="payment")

urlpatterns = router.urls