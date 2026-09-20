from decimal import Decimal
from django.db import transaction
from rest_framework import serializers
from config.serializers import BaseSerializer
from .models import Purchase, PurchaseItem
from ..products.models import Product
from ..stock.models import StockMovement
from ..stock.services import add_stock
from ..suppliers.models import Supplier


class PurchaseItemSerializer(BaseSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True )
    product = serializers.SlugRelatedField(slug_field="uuid", queryset=Product.objects.all())

    class Meta:
        model = PurchaseItem
        fields = ["uuid", "product", "product_name", "quantity", "unit_cost", "subtotal", ]
        read_only_fields = ["uuid", "subtotal", "product_name", ]

    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError(
                "Quantity must be greater than zero."
            )
        return value

    def validate_unit_cost(self, value):
        if value < 0:
            raise serializers.ValidationError(
                "Unit cost cannot be negative."
            )
        return value


class PurchaseSerializer(BaseSerializer):
    items = PurchaseItemSerializer(many=True)
    supplier = serializers.SlugRelatedField(slug_field="uuid", queryset=Supplier.objects.all())
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)

    class Meta:
        model = Purchase
        fields = [
            "uuid", "supplier", "supplier_name", "invoice_number", "status", "total", "purchase_date", "notes", "items", "created_at", "created_by",
                ]
        read_only_fields = ["uuid", "status", "created_at", "total", "created_by", "supplier_name"]
