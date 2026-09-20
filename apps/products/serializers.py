from rest_framework.serializers import Serializer
from rest_framework import serializers
from config.serializers import BaseSerializer
from .models import Category, Product, Brand, Unit


class CategorySerializer(BaseSerializer):
    class Meta:
        model = Category
        fields = ["uuid", "name", "description", "created_at", "created_by"]
        read_only_fields = ["uuid", "created_at", "created_by"]


class BrandSerializer(BaseSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    category = serializers.SlugRelatedField(slug_field="uuid", queryset=Category.objects.all())
    class Meta:
        model = Brand
        fields = ["uuid", "name", "category", "category_name", "created_at", "created_by"]
        read_only_fields = ["uuid", "category_name", "created_by"]


class UnitSerializer(BaseSerializer):
    class Meta:
        model = Unit
        fields = ["uuid", "name", "abbreviation", "quantity", "created_at", "created_by"]
        read_only_fields = ["uuid", "created_at", "created_by"]

class ProductSerializer(BaseSerializer):
    brand_name = serializers.CharField(source="brand.name", read_only=True)
    brand = serializers.SlugRelatedField(slug_field="uuid", queryset=Brand.objects.all())
    unit = serializers.SlugRelatedField(slug_field="uuid", queryset=Unit.objects.all())
    unit_name = serializers.CharField(source="unit.name", read_only=True)

    class Meta:
        model = Product
        fields = ["uuid", "brand", "brand_name", "name", "description", "unit", "unit_name", "buying_price",
                  "selling_price", "is_active","created_at", "updated_at" ]
        read_only_fields = ["uuid", "created_at", "updated_at"]


# class ProductVariantSerializer(BaseSerializers):
#     product = serializers.PrimaryKeyRelatedField(
#         queryset=Product.objects.all(), pk_field=serializers.UUIDField()
#     )
#     class Meta:
#         model = Product
#         fields = ["uuid", "product", "unit", "quantity_per_unit", "buying_price", "selling_price", "is_active",
#             "created_at", "updated_at", ]
#         read_only_fields = ["uuid", "created_at", "updated_at"]
