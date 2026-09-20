from rest_framework import serializers

from config.serializers import BaseSerializer
from .models import Stock, StockMovement
from ..products.models import Product


class StockSerializer(BaseSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    product = serializers.UUIDField(source="product.uuid", read_only=True)
    buying_price = serializers.DecimalField(
        source="product.buying_price",
        max_digits=12,
        decimal_places=2,
        read_only=True,
    )
    selling_price = serializers.DecimalField(
        source="product.selling_price",
        max_digits=12,
        decimal_places=2,
        read_only=True,
    )

    class Meta:
        model = Stock
        fields = [
            "uuid",
            "product",
            "product_name",
            "quantity",
            "buying_price",
            "selling_price",
            "updated_at",
        ]
        read_only_fields = [
            "uuid",
            "quantity",
            "updated_at",
            "product",
            "product_name",
            "buying_price",
            "selling_price",
        ]


class StockMovementSerializer(BaseSerializer):
    product = serializers.SlugRelatedField(
        slug_field="uuid",
        queryset=Product.objects.all(),
        write_only=True,
        required=False,
    )
    product_name = serializers.CharField(
        source="stock.product.name", read_only=True
    )

    class Meta:
        model = StockMovement
        fields = [
            "uuid",
            "product",
            "product_name",
            "movement_type",
            "quantity",
            "reference",
            "notes",
            "created_at",
        ]
        read_only_fields = [
            "uuid",
            "product_name",
            "created_at",
        ]

    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError(
                "Quantity must be greater than zero."
            )
        return value
