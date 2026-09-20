from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from rest_framework import serializers

from config.serializers import BaseSerializer
from .models import Sale, SaleItem
from ..customers.models import Customer
from ..products.models import Product
from ..stock.models import StockMovement
from ..stock.services import remove_stock


class SaleItemSerializer(BaseSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    product = serializers.SlugRelatedField(slug_field="uuid", queryset=Product.objects.all())

    class Meta:
        model = SaleItem
        fields = ["uuid", "product", "product_name", "quantity", "unit_price", "subtotal", ]
        read_only_fields = ["uuid", "subtotal", "product_name", ]

    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError(
                "Quantity must be greater than zero."
            )
        return value

    def validate_unit_price(self, value):
        if value < 0:
            raise serializers.ValidationError(
                "Unit price cannot be negative."
            )
        return value


class SaleSerializer(BaseSerializer):
    items = SaleItemSerializer(many=True)
    customer = serializers.SlugRelatedField(slug_field="uuid", queryset=Customer.objects.all())
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    paid_amount = serializers.SerializerMethodField()
    outstanding_balance = serializers.SerializerMethodField()

    class Meta:
        model = Sale
        fields = ["uuid", "customer", "customer_name", "status", "payment_status", "sale_date", "subtotal", "discount", "total",
            "notes", "items", "created_at", "paid_amount", "outstanding_balance", ]
        read_only_fields = ["uuid", "status", "subtotal", "total", "payment_status", "created_at", "paid_amount", "outstanding_balance", "notes"]

    def get_paid_amount(self, obj):
        return str(obj.payments.aggregate(total=Sum("amount"))["total"] or 0)

    def get_outstanding_balance(self, obj):
        paid = obj.payments.aggregate(total=Sum("amount"))["total"] or 0
        return str(obj.total - paid)

    def validate_discount(self, value):
        if value < 0:
            raise serializers.ValidationError("Discount cannot be negative.")
        return value

    def validate(self, attrs):
        items = attrs.get("items")
        if items is not None:
            product_ids = [item["product"].pk for item in items]
            if len(product_ids) != len(set(product_ids)):
                raise serializers.ValidationError({"items": "A product can appear only once."})
            subtotal = sum((item["quantity"] * item["unit_price"] for item in items), Decimal("0.00"))
            discount = attrs.get("discount", getattr(self.instance, "discount", Decimal("0.00")))
            if discount > subtotal:
                raise serializers.ValidationError({"discount": "Discount cannot exceed the sale subtotal."})
        return attrs
