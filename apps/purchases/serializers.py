from decimal import Decimal

from django.db import transaction
from rest_framework import serializers
from config.serializers import BaseSerializer, PositiveWholeNumberField
from config.reference_codes import format_reference
from .models import Purchase, PurchaseItem
from ..products.models import Product, ProductUnit, Unit
from ..stock.models import StockMovement
from ..stock.services import (
    add_stock,
    convert_to_base_quantity,
    remove_stock,
    validate_product_unit,
    validate_whole_quantity,
)
from ..suppliers.models import Supplier


class PurchaseItemSerializer(BaseSerializer):
    product_name = serializers.CharField(read_only=True)
    product = serializers.SlugRelatedField(
        slug_field="uuid", queryset=Product.objects.all()
    )
    product_unit = serializers.SlugRelatedField(
        slug_field="uuid", queryset=ProductUnit.objects.filter(is_active=True)
    )
    product_unit_name = serializers.CharField(source="unit_name", read_only=True)
    product_unit_abbreviation = serializers.CharField(source="unit_abbreviation", read_only=True)
    conversion_factor = serializers.IntegerField(source="conversion_factor_used", read_only=True)
    base_quantity = serializers.IntegerField(read_only=True)
    quantity = PositiveWholeNumberField()

    class Meta:
        model = PurchaseItem
        fields = [
            "uuid",
            "product",
            "product_name",
            "product_unit",
            "product_unit_name",
            "product_unit_abbreviation",
            "quantity",
            "conversion_factor",
            "base_quantity",
            "unit_cost",
            "subtotal",
        ]
        read_only_fields = [
            "uuid",
            "subtotal",
            "product_name",
            "product_unit_name",
            "product_unit_abbreviation",
            "conversion_factor",
            "base_quantity",
        ]

    def validate_unit_cost(self, value):
        if value < 0:
            raise serializers.ValidationError("Unit cost cannot be negative.")
        return value

    def validate(self, attrs):
        product = attrs["product"]
        product_unit = attrs.get("product_unit")
        quantity = attrs.get("quantity")

        if not product.is_active:
            raise serializers.ValidationError(
                {"product": f"{product.name} is not an active product."}
            )

        if quantity is None:
            raise serializers.ValidationError({"quantity": "Quantity is required."})

        try:
            validate_whole_quantity(quantity)
            validate_product_unit(product, product_unit)
        except ValueError as exc:
            message = str(exc)
            if "not configured for this product" in message:
                raise serializers.ValidationError({"product_unit": message}) from exc
            raise serializers.ValidationError({"quantity": message}) from exc

        return attrs


class PurchaseSerializer(BaseSerializer):
    items = PurchaseItemSerializer(many=True)
    supplier = serializers.SlugRelatedField(
        slug_field="uuid", queryset=Supplier.objects.all()
    )
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    reference_code = serializers.SerializerMethodField()

    def get_reference_code(self, obj: Purchase) -> str:
        return format_reference("PUR", obj.pk)

    class Meta:
        model = Purchase
        fields = [
            "uuid",
            "reference_code",
            "supplier",
            "supplier_name",
            "invoice_number",
            "status",
            "total",
            "purchase_date",
            "notes",
            "items",
            "created_at",
            "created_by",
        ]
        read_only_fields = [
            "uuid",
            "status",
            "created_at",
            "total",
            "created_by",
            "supplier_name",
        ]


class PurchaseCreateUpdateSerializer(PurchaseSerializer):
    """Serializer for creating/updating purchases with stock handling."""
    items = PurchaseItemSerializer(many=True)

    @transaction.atomic
    def create(self, validated_data):
        items_data = validated_data.pop("items", [])

        if self.context["request"].user.is_authenticated:
            validated_data["created_by"] = self.context["request"].user

        purchase = Purchase.objects.create(**validated_data)
        reference = format_reference("PUR", purchase.pk)

        total = Decimal("0.00")

        for item_data in items_data:
            quantity = item_data["quantity"]
            unit_cost = item_data["unit_cost"]
            product = item_data["product"]
            product_unit = item_data["product_unit"]

            # Calculate base quantity
            base_quantity = convert_to_base_quantity(product_unit, quantity)

            # Calculate subtotal
            subtotal = quantity * unit_cost

            # Create purchase item with snapshot data
            PurchaseItem.objects.create(
                purchase=purchase,
                product=product,
                product_unit=product_unit,
                quantity=quantity,
                conversion_factor_used=product_unit.conversion_factor,
                base_quantity=base_quantity,
                unit_cost=unit_cost,
                subtotal=subtotal,
                unit_name=product_unit.unit.name,
                unit_abbreviation=product_unit.unit.abbreviation or "",
                product_name=product.name,
                created_by=self.context["request"].user,
            )

            # Add to stock in base units. Any failure aborts the whole
            # transaction, so the purchase and its stock never diverge.
            try:
                add_stock(
                    product=product,
                    base_quantity=base_quantity,
                    movement_type=StockMovement.MovementTypes.PURCHASES,
                    reference=reference,
                    note=f"Purchase {reference}",
                    user=self.context["request"].user,
                    transaction_unit=product_unit.unit,
                    transaction_quantity=quantity,
                    conversion_factor_used=product_unit.conversion_factor,
                )
            except ValueError as exc:
                raise serializers.ValidationError({"items": str(exc)}) from exc

            total += subtotal

        purchase.total = total
        purchase.status = Purchase.Status.COMPLETED
        purchase.save(update_fields=["total", "status"])

        return purchase

    @transaction.atomic
    def update(self, instance, validated_data):
        if instance.status != Purchase.Status.COMPLETED:
            raise serializers.ValidationError("Only completed purchases can be modified.")

        items_data = validated_data.pop("items", None)

        # Update normal Purchase fields
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()

        if items_data is None:
            return instance

        reference = format_reference("PUR", instance.pk)

        # 1. Reverse old purchase items from stock
        old_items = list(instance.items.select_related("product", "product_unit__unit"))

        for item in old_items:
            remove_stock(
                product=item.product,
                base_quantity=item.base_quantity,
                movement_type=StockMovement.MovementTypes.PURCHASE_ADJUSTMENT,
                reference=reference,
                note="Reversing previous purchase item",
                user=self.context["request"].user,
            )

        # 2. Delete old purchase items
        instance.items.all().delete()

        # 3. Create new purchase items and add their stock
        total = Decimal("0.00")

        for item_data in items_data:
            product = item_data["product"]
            quantity = item_data["quantity"]
            unit_cost = item_data["unit_cost"]
            product_unit = item_data["product_unit"]

            base_quantity = convert_to_base_quantity(product_unit, quantity)
            subtotal = quantity * unit_cost

            PurchaseItem.objects.create(
                purchase=instance,
                product=product,
                product_unit=product_unit,
                quantity=quantity,
                conversion_factor_used=product_unit.conversion_factor,
                base_quantity=base_quantity,
                unit_cost=unit_cost,
                subtotal=subtotal,
                unit_name=product_unit.unit.name,
                unit_abbreviation=product_unit.unit.abbreviation or "",
                product_name=product.name,
                created_by=self.context["request"].user,
            )

            try:
                add_stock(
                    product=product,
                    base_quantity=base_quantity,
                    movement_type=StockMovement.MovementTypes.PURCHASE_ADJUSTMENT,
                    reference=reference,
                    note=f"Purchase {reference} updated",
                    user=self.context["request"].user,
                    transaction_unit=product_unit.unit,
                    transaction_quantity=quantity,
                    conversion_factor_used=product_unit.conversion_factor,
                )
            except ValueError as exc:
                raise serializers.ValidationError({"items": str(exc)}) from exc

            total += subtotal

        instance.total = total
        instance.status = Purchase.Status.COMPLETED
        instance.save(update_fields=["total", "status"])

        return instance