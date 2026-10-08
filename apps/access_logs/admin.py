from django.contrib import admin

from apps.access_logs.models import AccessLog


@admin.register(AccessLog)
class AccessLogAdmin(admin.ModelAdmin):
    """The log is readable in the admin and nothing more.

    Entries have no save permission and the table carries a trigger that rejects
    UPDATE and DELETE, so tampering here fails instead of succeeding quietly.
    """

    list_display = (
        "created_at",
        "event",
        "email_attempted",
        "ip_address",
        "city",
        "device_type",
        "browser_name",
        "is_new_device",
    )
    list_filter = ("event", "device_type", "is_new_device", "is_first_login", "created_at")
    search_fields = ("email_attempted", "ip_address", "city", "country", "user_agent")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False