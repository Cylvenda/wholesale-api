from django.db import models
from apps.customers.models import Customer
from apps.products.models import Product
from config.models import BaseModel


class Sale(BaseModel):

    class Status(models.TextChoices):
        DRAFT = "draft"
        COMPLETED = "completed"
        CANCELLED = "cancelled"

    class PaymentStatus(models.TextChoices):
        UNPAID = "unpaid"
        PARTIAL = "partial"
        PAID = "paid"

    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="sales")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    payment_status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.UNPAID)
    sale_date = models.DateTimeField()
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    notes = models.TextField(blank=True)


class SaleItem(BaseModel):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="sale_items")
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)

