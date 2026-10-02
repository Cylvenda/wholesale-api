from decimal import Decimal, InvalidOperation

from django.db import transaction
from rest_framework import serializers


class WholeNumberField(serializers.IntegerField):
    """An integer field that refuses fractional input such as ``1.5``.

    ``serializers.IntegerField`` happily truncates ``"1.5"`` to ``1``; inventory
    quantities must never do that, so the raw value is checked first.
    """

    default_error_messages = {
        "invalid_whole_number": "Enter a whole number.",
    }

    def to_internal_value(self, data):
        self._reject_fractions(data)
        return super().to_internal_value(data)

    def _reject_fractions(self, data):
        if isinstance(data, bool):
            self.fail("invalid_whole_number")
        if isinstance(data, float):
            if not data.is_integer():
                self.fail("invalid_whole_number")
            return
        if isinstance(data, Decimal):
            if data != data.to_integral_value():
                self.fail("invalid_whole_number")
            return
        if isinstance(data, str):
            text = data.strip()
            if not text:
                return
            try:
                parsed = Decimal(text)
            except (InvalidOperation, ValueError):
                self.fail("invalid")
            if parsed != parsed.to_integral_value():
                self.fail("invalid_whole_number")


class PositiveWholeNumberField(WholeNumberField):
    """Whole number of at least one, used for transaction quantities."""

    default_error_messages = {
        "invalid_whole_number": "Quantity must be a whole number greater than zero.",
    }

    def __init__(self, **kwargs):
        kwargs.setdefault("min_value", 1)
        super().__init__(**kwargs)


class BaseSerializer(serializers.ModelSerializer):

    @transaction.atomic
    def create(self, validated_data):
        request = self.context.get("request")

        if request and request.user.is_authenticated:
            validated_data["created_by"] = request.user

        return super().create(validated_data)

    class Meta:
        read_only_fields = [
            "id",
            "uuid",
            "created_by",
            "created_at",
            "updated_at",
        ]