from decimal import Decimal

from django.db.models import Sum
from rest_framework import serializers

from config.serializers import BaseSerializer, PositiveWholeNumberField
from config.reference_codes import format_reference
from .models import Sale, SaleItem
from ..customers.models import Customer
from ..products.models import Product, ProductUnit
from ..stock.models import StockMovement
from ..stock.services import (
    add_stock,
    convert_to_base_quantity,
    ensure_sale_quantity,
    remove_stock,
    validate_whole_quantity,
)


class SaleItemSerializer(BaseSerializer):
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
    # Retail vs wholesale is no longer chosen per line: it is kept only as a
    # historical label on sales recorded before the option was removed.
    sale_type = serializers.CharField(read_only=True)

    class Meta:
        model = SaleItem
        fields = [
            "uuid",
            "product",
            "product_name",
            "product_unit",
            "product_unit_name",
            "product_unit_abbreviation",
            "sale_type",
            "quantity",
            "conversion_factor",
            "base_quantity",
            "unit_price",
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
            "sale_type",
        ]

    def validate_unit_price(self, value):
        if value < 0:
            raise serializers.ValidationError("Unit price cannot be negative.")
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
            ensure_sale_quantity(product, product_unit, quantity)
        except ValueError as exc:
            message = str(exc)
            if "not configured for this product" in message:
                raise serializers.ValidationError({"product_unit": message}) from exc
            raise serializers.ValidationError({"quantity": message}) from exc

        return attrs


class SaleSerializer(BaseSerializer):
    items = SaleItemSerializer(many=True)
    customer = serializers.SlugRelatedField(
        slug_field="uuid", queryset=Customer.objects.all()
    )
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    paid_amount = serializers.SerializerMethodField()
    outstanding_balance = serializers.SerializerMethodField()
    reference_code = serializers.SerializerMethodField()

    def get_reference_code(self, obj: Sale) -> str:
        return format_reference("SAL", obj.pk)

    class Meta:
        model = Sale
        fields = [
            "uuid",
            "reference_code",
            "customer",
            "customer_name",
            "status",
            "payment_status",
            "sale_date",
            "subtotal",
            "discount",
            "total",
            "notes",
            "items",
            "created_at",
            "paid_amount",
            "outstanding_balance",
        ]
        read_only_fields = [
            "uuid",
            "status",
            "subtotal",
            "total",
            "payment_status",
            "created_at",
            "paid_amount",
            "outstanding_balance",
            "notes",
        ]

    def get_paid_amount(self, obj: Sale) -> str:
        return str(obj.payments.aggregate(total=Sum("amount"))["total"] or 0)

    def get_outstanding_balance(self, obj: Sale) -> str:
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
                raise serializers.ValidationError(
                    {"items": "A product can appear only once."}
                )
            subtotal = sum(
                (item["quantity"] * item["unit_price"] for item in items),
                Decimal("0.00"),
            )
            discount = attrs.get(
                "discount", getattr(self.instance, "discount", Decimal("0.00"))
            )
            if discount > subtotal:
                raise serializers.ValidationError(
                    {"discount": "Discount cannot exceed the sale subtotal."}
                )
        return attrs


class SaleCreateUpdateSerializer(SaleSerializer):
    """Serializer for creating/updating sales with stock handling."""

    items = SaleItemSerializer(many=True)

    def create(self, validated_data):
        items_data = validated_data.pop("items", [])

        if self.context["request"].user.is_authenticated:
            validated_data["created_by"] = self.context["request"].user

        sale = Sale.objects.create(**validated_data)
        reference = format_reference("SAL", sale.pk)

        total = Decimal("0.00")

        for item_data in items_data:
            quantity = item_data["quantity"]
            unit_price = item_data["unit_price"]
            product = item_data["product"]
            product_unit = item_data["product_unit"]
            # The form no longer sends a sale type; the model default applies.
            sale_type = SaleItem.SaleTypes.RETAIL

            # Re-check availability: stock may have moved since validation.
            try:
                base_quantity = ensure_sale_quantity(product, product_unit, quantity)
            except ValueError as exc:
                raise serializers.ValidationError({"items": str(exc)}) from exc

            try:
                remove_stock(
                    product=product,
                    base_quantity=base_quantity,
                    movement_type=StockMovement.MovementTypes.SALES,
                    reference=reference,
                    note=f"Sale {reference}",
                    user=self.context["request"].user,
                    transaction_unit=product_unit.unit,
                    transaction_quantity=quantity,
                    conversion_factor_used=product_unit.conversion_factor,
                )
            except ValueError as exc:
                raise serializers.ValidationError({"items": str(exc)}) from exc

            # Calculate subtotal
            subtotal = quantity * unit_price

            # Create sale item with snapshot data
            SaleItem.objects.create(
                sale=sale,
                product=product,
                product_unit=product_unit,
                sale_type=sale_type,
                quantity=quantity,
                conversion_factor_used=product_unit.conversion_factor,
                base_quantity=base_quantity,
                unit_price=unit_price,
                subtotal=subtotal,
                unit_name=product_unit.unit.name,
                unit_abbreviation=product_unit.unit.abbreviation or "",
                product_name=product.name,
                created_by=self.context["request"].user,
            )

            total += subtotal

        sale.subtotal = total
        sale.total = total - sale.discount
        sale.status = Sale.Status.COMPLETED
        sale.save(update_fields=["subtotal", "total", "status"])

        return sale

    def update(self, instance, validated_data):
        if instance.status != Sale.Status.COMPLETED:
            raise serializers.ValidationError("Only completed sales can be modified.")

        items_data = validated_data.pop("items", None)

        # Update Sale fields
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()

        if items_data is None:
            return instance

        reference = format_reference("SAL", instance.pk)

        # OLD ITEMS
        old_items = {
            item.product_id: item for item in instance.items.select_related("product", "product_unit__unit")
        }

        # NEW ITEMS
        new_items = {item_data["product"].id: item_data for item_data in items_data}

        total = Decimal("0.00")

        # Process old + new products
        product_ids = set(old_items) | set(new_items)

        for product_id in product_ids:
            old_item = old_items.get(product_id)
            new_item = new_items.get(product_id)

            old_base_quantity = int(old_item.base_quantity) if old_item else 0

            if new_item:
                new_base_quantity = convert_to_base_quantity(
                    new_item["product_unit"], new_item["quantity"]
                )
            else:
                new_base_quantity = 0

            difference = new_base_quantity - old_base_quantity

            # Sale reduces stock.
            # + difference -> remove more stock
            # - difference -> add stock back

            if difference > 0:
                if new_item is None:
                    raise serializers.ValidationError(
                        {"items": "A sale item is required for a stock increase."}
                    )

                try:
                    remove_stock(
                        product=new_item["product"],
                        base_quantity=difference,
                        movement_type=StockMovement.MovementTypes.SALES_ADJUSTMENT,
                        reference=reference,
                        note="Sale quantity increased",
                        user=self.context["request"].user,
                        transaction_unit=new_item["product_unit"].unit,
                        transaction_quantity=self._transaction_delta(old_item, new_item),
                        conversion_factor_used=new_item["product_unit"].conversion_factor,
                    )
                except ValueError as exc:
                    raise serializers.ValidationError({"items": str(exc)}) from exc

            elif difference < 0:
                add_back_quantity = abs(difference)
                product = old_item.product if old_item is not None else None
                if product is None and new_item is not None:
                    product = new_item["product"]
                if product is None:
                    raise serializers.ValidationError(
                        {"items": "A sale item is required for a stock return."}
                    )

                same_unit = (
                    old_item is not None
                    and new_item is not None
                    and old_item.product_unit_id == new_item["product_unit"].pk
                )

                add_stock(
                    product=product,
                    base_quantity=add_back_quantity,
                    movement_type=StockMovement.MovementTypes.SALES_ADJUSTMENT,
                    reference=reference,
                    note="Sale quantity decreased",
                    user=self.context["request"].user,
                    transaction_unit=old_item.product_unit.unit if same_unit else None,
                    transaction_quantity=(
                        abs(self._transaction_delta(old_item, new_item)) if same_unit else None
                    ),
                    conversion_factor_used=(
                        old_item.conversion_factor_used if same_unit else None
                    ),
                )

            # Calculate new total
            if new_item:
                total += new_item["quantity"] * new_item["unit_price"]

        # Replace SaleItems
        instance.items.all().delete()

        for item_data in items_data:
            quantity = item_data["quantity"]
            unit_price = item_data["unit_price"]
            product_unit = item_data["product_unit"]
            # The form no longer sends a sale type; the model default applies.
            sale_type = SaleItem.SaleTypes.RETAIL

            base_quantity = convert_to_base_quantity(product_unit, quantity)

            SaleItem.objects.create(
                sale=instance,
                product=item_data["product"],
                product_unit=product_unit,
                sale_type=sale_type,
                quantity=quantity,
                conversion_factor_used=product_unit.conversion_factor,
                base_quantity=base_quantity,
                unit_price=unit_price,
                subtotal=quantity * unit_price,
                unit_name=product_unit.unit.name,
                unit_abbreviation=product_unit.unit.abbreviation or "",
                product_name=item_data["product"].name,
                created_by=self.context["request"].user,
            )

        # Update sale total
        instance.subtotal = total
        instance.total = total - instance.discount
        instance.save(update_fields=["subtotal", "total"])

        return instance

    @staticmethod
    def _transaction_delta(old_item, new_item):
        """Whole-unit movement recorded for the audit trail on an edited sale."""
        new_quantity = int(new_item["quantity"])
        if old_item is not None and old_item.product_unit_id == new_item["product_unit"].pk:
            return new_quantity - int(old_item.quantity)
        return new_quantity