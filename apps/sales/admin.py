from django.contrib import admin

from apps.sales.models import Sale, SaleItem


class SaleItemInline(admin.TabularInline):
    model = SaleItem
    extra = 0
    fields = [
        "product",
        "product_unit",
        "sale_type",
        "quantity",
        "conversion_factor_used",
        "base_quantity",
        "unit_price",
        "subtotal",
    ]
    readonly_fields = [
        "uuid",
        "product_unit",
        "sale_type",
        "quantity",
        "conversion_factor_used",
        "base_quantity",
        "unit_price",
        "subtotal",
        "unit_name",
        "unit_abbreviation",
        "product_name",
    ]
    can_delete = False


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = [
        "get_reference_code",
        "customer",
        "status",
        "payment_status",
        "total",
        "sale_date",
        "created_at",
    ]
    list_filter = ["status", "payment_status"]
    search_fields = ["customer__name"]
    readonly_fields = ["uuid", "created_at", "updated_at", "created_by", "subtotal", "total", "payment_status"]
    inlines = [SaleItemInline]

    def get_reference_code(self, obj):
        from config.reference_codes import format_reference
        return format_reference("SAL", obj.pk)
    get_reference_code.short_description = "Reference"
    get_reference_code.admin_order_field = "pk"


@admin.register(SaleItem)
class SaleItemAdmin(admin.ModelAdmin):
    list_display = [
        "sale",
        "product",
        "product_unit",
        "sale_type",
        "quantity",
        "conversion_factor_used",
        "base_quantity",
        "unit_price",
        "subtotal",
    ]
    list_filter = ["sale_type", "product_unit__unit"]
    search_fields = ["product__name", "sale__reference_code"]
    readonly_fields = [
        "uuid",
        "created_at",
        "updated_at",
        "created_by",
        "product_unit",
        "sale_type",
        "quantity",
        "conversion_factor_used",
        "base_quantity",
        "unit_price",
        "subtotal",
        "unit_name",
        "unit_abbreviation",
        "product_name",
    ]