from django.contrib import admin

from apps.purchases.models import Purchase, PurchaseItem


class PurchaseItemInline(admin.TabularInline):
    model = PurchaseItem
    extra = 0
    fields = [
        "product",
        "product_unit",
        "quantity",
        "conversion_factor_used",
        "base_quantity",
        "unit_cost",
        "subtotal",
    ]
    readonly_fields = [
        "uuid",
        "product_unit",
        "quantity",
        "conversion_factor_used",
        "base_quantity",
        "unit_cost",
        "subtotal",
        "unit_name",
        "unit_abbreviation",
        "product_name",
    ]
    can_delete = False


@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display = [
        "get_reference_code",
        "supplier",
        "invoice_number",
        "status",
        "total",
        "purchase_date",
        "created_at",
    ]
    list_filter = ["status", "supplier"]
    search_fields = ["invoice_number", "supplier__name"]
    readonly_fields = ["uuid", "created_at", "updated_at", "created_by", "total", "status"]
    inlines = [PurchaseItemInline]

    def get_reference_code(self, obj):
        from config.reference_codes import format_reference
        return format_reference("PUR", obj.pk)
    get_reference_code.short_description = "Reference"
    get_reference_code.admin_order_field = "pk"


@admin.register(PurchaseItem)
class PurchaseItemAdmin(admin.ModelAdmin):
    list_display = [
        "purchase",
        "product",
        "product_unit",
        "quantity",
        "conversion_factor_used",
        "base_quantity",
        "unit_cost",
        "subtotal",
    ]
    list_filter = ["product_unit__unit"]
    search_fields = ["product__name", "purchase__invoice_number"]
    readonly_fields = [
        "uuid",
        "created_at",
        "updated_at",
        "created_by",
        "product_unit",
        "quantity",
        "conversion_factor_used",
        "base_quantity",
        "unit_cost",
        "subtotal",
        "unit_name",
        "unit_abbreviation",
        "product_name",
    ]