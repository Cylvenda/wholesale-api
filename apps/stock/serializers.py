from rest_framework import serializers

from config.serializers import BaseSerializer, PositiveWholeNumberField
from .models import Stock, StockMovement
from .services import base_unit_price, get_base_unit_config, validate_product_unit
from apps.products.models import Product, ProductUnit


class StockSerializer(BaseSerializer):
    # Exposed as the product uuid so clients can match a stock row to a product
    # the same way every other endpoint does.
    product = serializers.SlugRelatedField(slug_field="uuid", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    base_unit_name = serializers.CharField(source="product.base_unit.name", read_only=True)
    base_unit_abbreviation = serializers.CharField(source="product.base_unit.abbreviation", read_only=True)
    # Priced from the base unit's own configuration: stock is counted in base
    # units, so this is the price one base unit actually costs.
    buying_price = serializers.SerializerMethodField()
    selling_price = serializers.DecimalField(source="product.selling_price", max_digits=12, decimal_places=2, read_only=True)
    quantity = serializers.IntegerField(read_only=True)
    formatted_quantity = serializers.SerializerMethodField()
    base_display = serializers.SerializerMethodField()

    class Meta:
        model = Stock
        fields = [
            "uuid",
            "product",
            "product_name",
            "quantity",
            "formatted_quantity",
            "base_display",
            "base_unit_name",
            "base_unit_abbreviation",
            "buying_price",
            "selling_price",
            "updated_at",
        ]
        read_only_fields = ["uuid", "updated_at"]

    def get_buying_price(self, obj):
        # Returned as an exact string: a raw Decimal here would be encoded by
        # the JSON renderer as a float and lose its cents.
        return str(base_unit_price(obj.product))

    def get_formatted_quantity(self, obj):
        """Human readable stock, e.g. ``9 CS + 23 Chupa`` for 239 base units."""
        from apps.stock.services import format_stock_quantity

        return format_stock_quantity(obj.product, obj.quantity)

    def get_base_display(self, obj):
        base_label = obj.product.base_unit.abbreviation or obj.product.base_unit.name
        return f"{int(obj.quantity)} {base_label}"


class StockMovementSerializer(BaseSerializer):
    product_name = serializers.CharField(source="stock.product.name", read_only=True)
    transaction_unit_name = serializers.CharField(read_only=True)
    base_unit_name = serializers.CharField(read_only=True)

    class Meta:
        model = StockMovement
        fields = [
            "uuid",
            "movement_type",
            "quantity",
            "base_quantity",
            "base_unit_name",
            "transaction_quantity",
            "transaction_unit_name",
            "conversion_factor_used",
            "reference",
            "notes",
            "product_name",
            "created_at",
            "created_by",
        ]
        read_only_fields = ["uuid", "created_at", "created_by"]


class StockAdjustmentSerializer(serializers.Serializer):
    """A stocktake counted in one of the product's configured units.

    The shopkeeper counts what they can see - crates, bottles, bags - so the
    chosen ``product_unit`` decides the conversion. Omitting it falls back to
    the product's base unit, where one counted unit is one base unit.
    """

    product = serializers.SlugRelatedField(
        slug_field="uuid", queryset=Product.objects.all()
    )
    product_unit = serializers.SlugRelatedField(
        slug_field="uuid",
        queryset=ProductUnit.objects.filter(is_active=True),
        required=False,
        allow_null=True,
    )
    movement_type = serializers.ChoiceField(choices=StockMovement.MovementTypes.choices)
    quantity = PositiveWholeNumberField()
    notes = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        product = attrs["product"]
        if not product.is_active:
            raise serializers.ValidationError(
                {"product": f"{product.name} is not an active product."}
            )

        product_unit = attrs.get("product_unit")
        if product_unit is None:
            product_unit = get_base_unit_config(product)
            if product_unit is None:
                raise serializers.ValidationError(
                    {
                        "product_unit": (
                            f"{product.name} has no base unit configured. "
                            "Configure its units before recording an adjustment."
                        )
                    }
                )

        try:
            validate_product_unit(product, product_unit)
        except ValueError as exc:
            message = str(exc)
            field = "product" if "not configured for this product" in message else "product_unit"
            raise serializers.ValidationError({field: message}) from exc

        attrs["product_unit"] = product_unit
        return attrs


class UnitAvailabilitySerializer(serializers.Serializer):
    """Availability of stock expressed in one configured selling unit.

    ``available_quantity`` is the number of WHOLE units the shop may sell in
    the selected unit; ``remainder_base_quantity`` is what is left over in base
    units and can only be sold by switching to a smaller unit.
    """

    base_stock = serializers.IntegerField()
    base_unit = serializers.CharField()
    base_unit_abbreviation = serializers.CharField(allow_null=True)
    selected_unit = serializers.CharField(allow_null=True)
    conversion_factor = serializers.IntegerField(allow_null=True)
    available_quantity = serializers.IntegerField()
    remainder_base_quantity = serializers.IntegerField()
    available_display = serializers.CharField()
    base_display = serializers.CharField()