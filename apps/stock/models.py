from django.db import models

from apps.products.models import Product
from config.models import BaseModel


class Stock(BaseModel):
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
    movement_type = models.CharField(max_length=20, choices=MovementTypes.choices)
    quantity = models.PositiveIntegerField(default=0)
    reference = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
