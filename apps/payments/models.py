from django.db import models
from apps.customers.models import Customer
from apps.sales.models import Sale
from config.models import BaseModel

class Payment(BaseModel):
    PAYMENT_METHODS = [
        ("cash", "Cash"),
        ("mobile_money", "Mobile Money"),
        ("bank", "Bank"),
        ("other", "Other"),
    ]

    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="payments")
    sale = models.ForeignKey(Sale, on_delete=models.PROTECT, related_name="payments", null=True, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    method = models.CharField(max_length=30, choices=PAYMENT_METHODS)
    reference = models.CharField(max_length=100, blank=True)
    payment_date = models.DateTimeField()
    notes = models.TextField(blank=True)
