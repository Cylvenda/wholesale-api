import re
from uuid import UUID

from rest_framework import serializers

from config.serializers import BaseSerializer
from config.reference_codes import format_reference
from .models import Stock, StockMovement
from ..products.models import Product


class StockSerializer(BaseSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    product = serializers.UUIDField(source="product.uuid", read_only=True)
    unit_name = serializers.SerializerMethodField()
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
            "unit_name",
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
            "unit_name",
            "buying_price",
            "selling_price",
        ]

    def get_unit_name(self, obj):
        unit = obj.product.unit
        return f"{unit.name} ({unit.abbreviation})" if unit.abbreviation else unit.name


class StockMovementSerializer(BaseSerializer):
    product = serializers.SlugRelatedField(
        slug_field="uuid",
        queryset=Product.objects.all(),
        write_only=True,
        required=False,
    )
    product_name = serializers.CharField(source="stock.product.name", read_only=True)
    unit_name = serializers.SerializerMethodField()

    class Meta:
        model = StockMovement
        fields = [
            "uuid",
            "product",
            "product_name",
            "unit_name",
            "movement_type",
            "quantity",
            "reference",
            "notes",
            "created_at",
        ]
        read_only_fields = [
            "uuid",
            "product_name",
            "unit_name",
            "created_at",
        ]

    def get_unit_name(self, obj):
        unit = obj.stock.product.unit
        return f"{unit.name} ({unit.abbreviation})" if unit.abbreviation else unit.name

    def to_representation(self, instance):
        data = super().to_representation(instance)
        raw_reference = str(instance.reference or "")
        reference = raw_reference

        try:
            reference_uuid = UUID(raw_reference)
        except (ValueError, TypeError, AttributeError):
            reference_uuid = None

        if reference_uuid:
            from apps.purchases.models import Purchase
            from apps.sales.models import Sale

            movement_type = instance.movement_type.lower()
            if "purchase" in movement_type:
                purchase_id = (
                    Purchase.objects.filter(uuid=reference_uuid)
                    .values_list("pk", flat=True)
                    .first()
                )
                reference = (
                    format_reference("PUR", purchase_id)
                    if purchase_id
                    else f"PUR-{reference_uuid.hex[:8].upper()}"
                )
            elif "sale" in movement_type:
                sale_id = (
                    Sale.objects.filter(uuid=reference_uuid)
                    .values_list("pk", flat=True)
                    .first()
                )
                reference = (
                    format_reference("SAL", sale_id)
                    if sale_id
                    else f"SAL-{reference_uuid.hex[:8].upper()}"
                )
            else:
                purchase_id = (
                    Purchase.objects.filter(uuid=reference_uuid)
                    .values_list("pk", flat=True)
                    .first()
                )
                sale_id = (
                    Sale.objects.filter(uuid=reference_uuid)
                    .values_list("pk", flat=True)
                    .first()
                )
                if purchase_id:
                    reference = format_reference("PUR", purchase_id)
                elif sale_id:
                    reference = format_reference("SAL", sale_id)
                else:
                    reference = f"MOV-{reference_uuid.hex[:8].upper()}"

        data["reference"] = reference
        notes = str(data.get("notes") or "")
        if raw_reference and raw_reference != reference:
            notes = notes.replace(raw_reference, reference)
        data["notes"] = re.sub(
            r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
            "related item",
            notes,
        )
        return data

    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError("Quantity must be greater than zero.")
        return value
