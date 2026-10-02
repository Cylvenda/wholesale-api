from django.contrib import admin
from .models import Category, Brand, Product, Unit, ProductUnit


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "description", "created_at", "created_by"]
    search_fields = ["name"]
    readonly_fields = ["uuid", "created_at", "updated_at", "created_by"]


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ["name", "category", "created_at", "created_by"]
    list_filter = ["category"]
    search_fields = ["name"]
    readonly_fields = ["uuid", "created_at", "updated_at", "created_by"]


class ProductUnitInline(admin.TabularInline):
    model = ProductUnit
    extra = 1
    fields = ["unit", "conversion_factor", "buying_price", "selling_price", "is_active"]
    readonly_fields = ["uuid", "created_at", "updated_at", "created_by"]


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ["name", "brand", "base_unit", "buying_price", "selling_price", "is_active", "created_at"]
    list_filter = ["brand", "base_unit", "is_active"]
    search_fields = ["name", "brand__name"]
    readonly_fields = ["uuid", "created_at", "updated_at", "created_by"]
    inlines = [ProductUnitInline]


@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    list_display = ["name", "abbreviation", "is_active", "created_at", "created_by"]
    list_filter = ["is_active"]
    search_fields = ["name", "abbreviation"]
    readonly_fields = ["uuid", "created_at", "updated_at", "created_by"]


@admin.register(ProductUnit)
class ProductUnitAdmin(admin.ModelAdmin):
    list_display = ["product", "unit", "conversion_factor", "buying_price", "selling_price", "is_active", "created_at"]
    list_filter = ["product", "unit", "is_active"]
    search_fields = ["product__name", "unit__name"]
    readonly_fields = ["uuid", "created_at", "updated_at", "created_by"]