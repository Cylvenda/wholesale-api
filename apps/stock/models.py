from django.db import models

from apps.products.models import Product, Unit
from config.models import BaseModel


class Stock(BaseModel):
    """Stock on hand, always stored in the product's BASE unit (whole units)."""

    product = models.OneToOneField(Product, on_delete=models.PROTECT, related_name="stock")
    quantity = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.product.name} - {self.quantity}"


class StockMovement(BaseModel):
    class MovementTypes(models.TextChoices):
        INITIAL = "Initial Stock"
        PURCHASES = "Purchases"
        SALES = "Sales"
        PURCHASE_ADJUSTMENT = "Purchase Adjustment"
        SALES_ADJUSTMENT = "Sales Adjustment"
        RETURN = "Return"
        DAMAGES = "Damages"
        CANCEL = "Cancellation"
        STOCKTAKE_SURPLUS = "Stocktake Surplus"
        STOCKTAKE_LOSS = "Stocktake Loss"

    stock = models.ForeignKey(Stock, on_delete=models.PROTECT, related_name="movements")
    movement_type = models.CharField(max_length=30, choices=MovementTypes.choices)
    quantity = models.PositiveIntegerField(default=0)
    reference = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)

    # Transaction unit tracking (for audit/history)
    transaction_unit = models.ForeignKey(
        Unit,
        on_delete=models.PROTECT,
        related_name="stock_movements",
        null=True,
        blank=True,
    )
    transaction_quantity = models.PositiveIntegerField(null=True, blank=True)
    transaction_unit_name = models.CharField(max_length=50, blank=True)
    conversion_factor_used = models.PositiveIntegerField(null=True, blank=True)
    base_unit = models.ForeignKey(
        Unit,
        on_delete=models.PROTECT,
        related_name="base_stock_movements",
        null=True,
        blank=True,
    )
    base_quantity = models.PositiveIntegerField(null=True, blank=True)
    base_unit_name = models.CharField(max_length=50, blank=True)