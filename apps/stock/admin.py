from django.contrib import admin

from apps.stock.models import Stock, StockMovement


@admin.register(Stock)
class StockAdmin(admin.ModelAdmin):
    list_display = ["product", "quantity", "updated_at", "created_by"]
    search_fields = ["product__name"]
    readonly_fields = ["uuid", "created_at", "updated_at", "created_by"]


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = [
        "stock",
        "movement_type",
        "quantity",
        "base_quantity",
        "base_unit_name",
        "transaction_quantity",
        "transaction_unit_name",
        "conversion_factor_used",
        "reference",
        "created_at",
    ]
    list_filter = ["movement_type", "transaction_unit", "base_unit"]
    search_fields = ["stock__product__name", "reference"]
    readonly_fields = ["uuid", "created_at", "created_by"]