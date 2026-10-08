"""Query filters for the access log list."""

import django_filters as filters
from django.db.models import Q

from apps.access_logs.models import AccessLog


class AccessLogFilter(filters.FilterSet):
    """Filter the log down to the accounts, addresses or window of interest."""

    date_from = filters.DateTimeFilter(field_name="created_at", lookup_expr="gte")
    date_to = filters.DateTimeFilter(field_name="created_at", lookup_expr="lte")
    ip_address = filters.CharFilter(field_name="ip_address", lookup_expr="iexact")
    ip_contains = filters.CharFilter(field_name="ip_address", lookup_expr="icontains")
    country = filters.CharFilter(field_name="country", lookup_expr="iexact")
    city = filters.CharFilter(field_name="city", lookup_expr="icontains")
    search = filters.CharFilter(method="filter_search")

    class Meta:
        model = AccessLog
        fields = ["event", "user", "is_new_device", "is_first_login", "device_type"]

    def filter_search(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(
            Q(email_attempted__icontains=value)
            | Q(user__email__icontains=value)
            | Q(ip_address__icontains=value)
            | Q(user_agent__icontains=value)
            | Q(city__icontains=value)
            | Q(country__icontains=value)
            | Q(device_type__icontains=value)
        )