from rest_framework import serializers
from config.serializers import BaseSerializer
from .models import BusinessDetails, ReportSettings


class BusinessDetailsSerializer(BaseSerializer):
    class Meta:
        model = BusinessDetails
        fields = [
            "uuid", "name", "address", "phone", "email", "tax_number",
            "receipt_footer", "is_active", "created_at", "updated_at",
        ]
        read_only_fields = ["uuid", "created_at", "updated_at"]


class ReportSettingsSerializer(BaseSerializer):
    class Meta:
        model = ReportSettings
        fields = ["uuid", "default_from_days", "include_tax_on_receipt"]
        read_only_fields = ["uuid", "created_at", "updated_at"]


class ReceiptQueryParamsSerializer(serializers.Serializer):
    """Validates query parameters for the receipt endpoint."""
    from_date = serializers.DateField(required=False, allow_null=True)
    to_date = serializers.DateField(required=False, allow_null=True)
    product = serializers.UUIDField(required=False, allow_null=True)
    supplier = serializers.UUIDField(required=False, allow_null=True)
    customer = serializers.UUIDField(required=False, allow_null=True)