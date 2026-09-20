from rest_framework import serializers
from decimal import Decimal
from .models import Payment
from apps.sales.models import Sale


class PaymentSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    sale = serializers.SlugRelatedField(
        slug_field="uuid",
        queryset=Sale.objects.all(),
    )

    class Meta:
        model = Payment
        fields = ["uuid", "customer", "customer_name", "sale", "amount", "method", "reference", "payment_date",
            "notes", "created_at", ]

        read_only_fields = ["uuid", "created_at", "customer_name", "customer"]

    def validate_amount(self, value):
        if value <= Decimal("0"):
            raise serializers.ValidationError(
                "Payment amount must be greater than zero."
            )

        return value

    def validate(self, attrs):
        sale = attrs.get("sale", getattr(self.instance, "sale", None))
        amount = attrs.get("amount", getattr(self.instance, "amount", None))

        if not sale:
            raise serializers.ValidationError({"sale": "Sale is required."})

        if sale.status != "completed":
            raise serializers.ValidationError({
                "sale": "Payment can only be made for a completed sale."
            })

        if self.instance and "sale" in attrs and sale.pk != self.instance.sale_id:
            raise serializers.ValidationError({"sale": "A payment's sale cannot be changed."})

        if amount is None:
            raise serializers.ValidationError({"amount": "This field is required."})

        return attrs
