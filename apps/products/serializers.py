from decimal import Decimal

from rest_framework import serializers
from config.serializers import BaseSerializer, PositiveWholeNumberField
from .models import Category, Product, Brand, Unit, ProductUnit


class CategorySerializer(BaseSerializer):
    class Meta:
        model = Category
        fields = ["uuid", "name", "description", "created_at", "created_by"]
        read_only_fields = ["uuid", "created_at", "created_by"]


class BrandSerializer(BaseSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    category = serializers.SlugRelatedField(
        slug_field="uuid", queryset=Category.objects.all()
    )

    class Meta:
        model = Brand
        fields = [
            "uuid",
            "name",
            "category",
            "category_name",
            "created_at",
            "created_by",
        ]
        read_only_fields = ["uuid", "category_name", "created_by"]


class UnitSerializer(BaseSerializer):
    class Meta:
        model = Unit
        fields = [
            "uuid",
            "name",
            "abbreviation",
            "is_active",
            "created_at",
            "created_by",
        ]
        read_only_fields = ["uuid", "created_at", "created_by"]


class ProductUnitSerializer(BaseSerializer):
    unit_name = serializers.CharField(source="unit.name", read_only=True)
    unit_abbreviation = serializers.CharField(source="unit.abbreviation", read_only=True)
    unit = serializers.SlugRelatedField(
        slug_field="uuid", queryset=Unit.objects.filter(is_active=True)
    )
    conversion_factor = PositiveWholeNumberField(help_text="How many base units one of this unit contains.")

    class Meta:
        model = ProductUnit
        fields = [
            "uuid",
            "unit",
            "unit_name",
            "unit_abbreviation",
            "conversion_factor",
            "buying_price",
            "selling_price",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["uuid", "created_at", "updated_at", "unit_name", "unit_abbreviation"]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        product = getattr(self.instance, "product", None)
        product = product or self.context.get("product")
        factor = attrs.get("conversion_factor")
        unit = attrs.get("unit") or getattr(self.instance, "unit", None)

        if factor is not None and factor < 1:
            raise serializers.ValidationError(
                {"conversion_factor": "Conversion factor must be a whole number of at least 1."}
            )

        if (
            product is not None
            and unit is not None
            and factor is not None
            and unit.pk == product.base_unit_id
            and factor != 1
        ):
            raise serializers.ValidationError(
                {"conversion_factor": "The base unit must have a conversion factor of 1."}
            )

        return attrs


class ProductSerializer(BaseSerializer):
    brand_name = serializers.CharField(source="brand.name", read_only=True)
    category_name = serializers.CharField(source="brand.category.name", read_only=True)
    brand = serializers.SlugRelatedField(
        slug_field="uuid", queryset=Brand.objects.all()
    )
    base_unit = serializers.SlugRelatedField(
        slug_field="uuid", queryset=Unit.objects.filter(is_active=True)
    )
    base_unit_name = serializers.CharField(source="base_unit.name", read_only=True)
    base_unit_abbreviation = serializers.CharField(source="base_unit.abbreviation", read_only=True)
    product_units = ProductUnitSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = [
            "uuid",
            "brand",
            "brand_name",
            "category_name",
            "name",
            "description",
            "base_unit",
            "base_unit_name",
            "base_unit_abbreviation",
            "buying_price",
            "selling_price",
            "is_active",
            "created_at",
            "updated_at",
            "product_units",
        ]
        read_only_fields = ["uuid", "created_at", "updated_at", "brand_name", "category_name", "base_unit_name", "base_unit_abbreviation"]


class ProductCreateUpdateSerializer(BaseSerializer):
    """Serializer for creating/updating products with nested ProductUnits."""
    brand = serializers.SlugRelatedField(
        slug_field="uuid", queryset=Brand.objects.all()
    )
    base_unit = serializers.SlugRelatedField(
        slug_field="uuid", queryset=Unit.objects.filter(is_active=True)
    )
    product_units = ProductUnitSerializer(many=True, required=False)

    class Meta:
        model = Product
        fields = [
            "uuid",
            "brand",
            "name",
            "description",
            "base_unit",
            "buying_price",
            "selling_price",
            "is_active",
            "product_units",
        ]
        read_only_fields = ["uuid"]

    def validate(self, attrs):
        base_unit = attrs.get("base_unit", getattr(self.instance, "base_unit", None))
        product_units_data = attrs.get("product_units")

        if product_units_data is not None:
            unit_ids = [data["unit"].pk for data in product_units_data]
            if len(unit_ids) != len(set(unit_ids)):
                raise serializers.ValidationError(
                    {"product_units": "A unit can only be configured once per product."}
                )

            for data in product_units_data:
                factor = data.get("conversion_factor")
                if factor is None or factor < 1:
                    raise serializers.ValidationError(
                        {
                            "product_units": "Each unit needs a whole-number conversion factor of at least 1."
                        }
                    )
                if data["unit"].pk != base_unit.pk and factor == 1:
                    raise serializers.ValidationError(
                        {
                            "product_units": (
                                f"{data['unit'].name} is not the base unit, so its conversion "
                                "factor must be greater than 1 (how many base units it holds)."
                            )
                        }
                    )

            base_entry = next(
                (data for data in product_units_data if data["unit"].pk == getattr(base_unit, "pk", None)),
                None,
            )
            if base_entry is None:
                raise serializers.ValidationError(
                    {
                        "product_units": "The base unit must be configured in the unit table."
                    }
                )
            if base_entry["conversion_factor"] != 1:
                raise serializers.ValidationError(
                    {
                        "product_units": "The base unit must have a conversion factor of 1."
                    }
                )

        return attrs

    def create(self, validated_data):
        product_units_data = validated_data.pop("product_units", [])
        base_unit = validated_data["base_unit"]
        product = Product.objects.create(**validated_data)

        user = self.context["request"].user

        # The base unit always has its own configuration row with a factor of 1.
        base_entry = next(
            (data for data in product_units_data if data["unit"].pk == base_unit.pk),
            None,
        )

        ProductUnit.objects.create(
            product=product,
            unit=base_unit,
            conversion_factor=1,
            buying_price=(
                base_entry["buying_price"]
                if base_entry
                else validated_data.get("buying_price", Decimal("0.00"))
            ),
            selling_price=(
                base_entry["selling_price"]
                if base_entry
                else validated_data.get("selling_price", Decimal("0.00"))
            ),
            is_active=True,
            created_by=user,
        )

        for pu_data in product_units_data:
            if pu_data["unit"].pk == base_unit.pk:
                continue
            ProductUnit.objects.create(
                created_by=user,
                **pu_data,
                product=product,
            )

        return product

    def update(self, instance, validated_data):
        product_units_data = validated_data.pop("product_units", None)

        # Update product fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # Update product units if provided
        if product_units_data is not None:
            existing_units = {pu.unit_id: pu for pu in instance.product_units.all()}
            seen_unit_ids = set()

            for pu_data in product_units_data:
                unit = pu_data["unit"]
                seen_unit_ids.add(unit.id)

                if unit.id in existing_units:
                    # Update existing
                    pu = existing_units[unit.id]
                    for attr, value in pu_data.items():
                        if attr != "unit":
                            setattr(pu, attr, value)
                    pu.save()
                else:
                    # Create new
                    ProductUnit.objects.create(
                        product=instance,
                        created_by=self.context["request"].user,
                        **pu_data
                    )

            # Deactivate units not in the update
            for unit_id, pu in existing_units.items():
                if unit_id not in seen_unit_ids:
                    pu.is_active = False
                    pu.save()

        return instance