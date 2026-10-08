"""Read-only API over the access log."""

from django.utils import timezone
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response

from apps.access_logs.filters import AccessLogFilter
from apps.access_logs.models import AccessLog


class AccessLogSerializer(serializers.ModelSerializer):
    """Every field is derived; nothing here is accepted as input."""

    user_email = serializers.EmailField(read_only=True)
    user_name = serializers.SerializerMethodField()
    device = serializers.SerializerMethodField()

    class Meta:
        model = AccessLog
        fields = [
            "id",
            "uuid",
            "created_at",
            "user",
            "user_email",
            "user_name",
            "email_attempted",
            "event",
            "reason",
            "ip_address",
            "ip_version",
            "user_agent",
            "device_type",
            "os_name",
            "browser_name",
            "device",
            "country",
            "country_code",
            "region",
            "city",
            "latitude",
            "longitude",
            "is_first_login",
            "is_new_device",
            "previous_ip_address",
            "previous_login_at",
            "failed_attempts_before",
            "previous_hash",
            "entry_hash",
        ]
        read_only_fields = fields

    def get_user_name(self, obj):
        if obj.user is None:
            return ""
        return obj.user.full_name or obj.user.email

    def get_device(self, obj):
        parts = [obj.device_type, obj.os_name, obj.browser_name]
        return " · ".join(part for part in parts if part) or "Unknown device"


class AccessLogViewSet(viewsets.ReadOnlyModelViewSet):
    """The access log can be read and filtered, never written to or removed."""

    serializer_class = AccessLogSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]
    filterset_class = AccessLogFilter
    search_fields = ["email_attempted", "ip_address", "user__email", "city", "country"]
    # The project sets no default filter backends, so they are attached here
    # rather than changing filtering for every other endpoint.
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    ordering_fields = ["created_at", "event", "ip_address"]
    ordering = ["-created_at", "-id"]

    def get_queryset(self):
        return AccessLog.objects.select_related("user")

    @action(detail=False, methods=["get"], url_path="summary")
    def summary(self, request):
        """Headline counts for the access-log page header."""
        today = timezone.now().date()
        logs = AccessLog.objects.all()
        return Response(
            {
                "total": logs.count(),
                "successful_logins": logs.filter(event=AccessLog.Event.LOGIN_SUCCESS).count(),
                "failed_attempts": logs.filter(event=AccessLog.Event.LOGIN_FAILURE).count(),
                "logins_today": logs.filter(
                    event=AccessLog.Event.LOGIN_SUCCESS, created_at__date=today
                ).count(),
                "distinct_ips": logs.values("ip_address").distinct().count(),
                "new_devices": logs.filter(is_new_device=True).count(),
            }
        )

    @action(detail=False, methods=["get"], url_path="integrity")
    def integrity(self, request):
        """Report whether the hash chain still matches the stored rows."""
        first = AccessLog.objects.order_by("id").first()
        if first is None:
            return Response({"entries": 0, "intact": True, "first_broken_entry": None})
        broken = first.verify_chain()
        return Response(
            {
                "entries": AccessLog.objects.count(),
                "intact": broken is None,
                "first_broken_entry": broken.id if broken else None,
                "checked_at": AccessLog.objects.order_by("-id")
                .values_list("created_at", flat=True)
                .first(),
            }
        )
