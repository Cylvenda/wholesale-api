from rest_framework import serializers
from decimal import Decimal
from django.db.models import Sum
from config.money import to_money
from .models import Payment
from apps.sales.models import Sale
from config.reference_codes import format_reference


class PaymentSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    reference_code = serializers.SerializerMethodField()
    sale = serializers.SlugRelatedField(
        slug_field="uuid",
        queryset=Sale.objects.all(),
    )
    # What this payment moved, in the same exact money as the sale it settles.
    sale_total = serializers.DecimalField(
        source="sale.total", max_digits=12, decimal_places=2, read_only=True
    )
    amount_paid = serializers.SerializerMethodField()
    outstanding_balance = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = [
            "uuid",
            "reference_code",
            "customer",
            "customer_name",
            "sale",
            "amount",
            "sale_total",
            "amount_paid",
            "outstanding_balance",
            "method",
            "reference",
            "payment_date",
            "notes",
            "created_at",
        ]

        read_only_fields = [
            "uuid",
            "created_at",
            "customer_name",
            "customer",
            "reference",
        ]

    def get_amount_paid(self, obj) -> str:
        """Total received against the sale, including this payment."""
        paid = to_money(obj.sale.payments.aggregate(total=Sum("amount"))["total"])
        return str(paid)

    def get_outstanding_balance(self, obj) -> str:
        """What is still owed on the sale this payment belongs to."""
        if obj.sale_id is None:
            return str(Decimal("0.00"))
        paid = to_money(obj.sale.payments.aggregate(total=Sum("amount"))["total"])
        balance = to_money(obj.sale.total) - paid
        return str(balance if balance > 0 else Decimal("0.00"))

    def create(self, validated_data):
        """The payment reference is generated here, never typed by the user."""
        payment = super().create(validated_data)
        if not payment.reference:
            payment.reference = format_reference("PAY", payment.pk)
            payment.save(update_fields=["reference"])
        return payment

    def get_reference_code(self, obj):
        return format_reference("PAY", obj.pk)

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
            raise serializers.ValidationError(
                {"sale": "Payment can only be made for a completed sale."}
            )

        if self.instance and "sale" in attrs and sale.pk != self.instance.sale_id:
            raise serializers.ValidationError(
                {"sale": "A payment's sale cannot be changed."}
            )

        if amount is None:
            raise serializers.ValidationError({"amount": "This field is required."})

        return attrs
