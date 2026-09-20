from django.db import models

from apps.products.models import Product
from apps.suppliers.models import Supplier
from config.models import BaseModel


class Purchase(BaseModel):
    class Status(models.TextChoices):
        DRAFT = "draft"
        COMPLETED = "completed"
        CANCELLED = "cancelled"

    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="purchases")
    invoice_number = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default="draft")
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    purchase_date = models.DateTimeField()
    notes = models.TextField(blank=True)


class PurchaseItem(BaseModel):
    purchase = models.ForeignKey(Purchase, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="purchase_items")
    quantity = models.PositiveIntegerField()
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
