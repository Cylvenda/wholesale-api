from rest_framework.routers import DefaultRouter

from apps.access_logs.views import AccessLogViewSet

router = DefaultRouter()
router.register(
    "access-logs",
    AccessLogViewSet,
    basename="access-logs",
)

urlpatterns = router.urls