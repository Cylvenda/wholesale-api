from django.db import models
from config.models import BaseModel


class BusinessDetails(BaseModel):
    """Business information printed on receipts and reports."""

    name = models.CharField(max_length=150, default="IMARA SHOP")
    address = models.TextField(blank=True, default="")
    phone = models.CharField(max_length=30, blank=True, default="")
    email = models.EmailField(blank=True, default="")
    tax_number = models.CharField(max_length=50, blank=True, default="")
    receipt_footer = models.TextField(
        blank=True,
        default="Thank you for your business. Goods sold are not returnable.",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # Keep only one active business record.
        if self.is_active:
            BusinessDetails.objects.filter(is_active=True).exclude(
                pk=self.pk
            ).update(is_active=False)
        super().save(*args, **kwargs)


class ReportSettings(BaseModel):
    """Report/export configuration."""

    default_from_days = models.PositiveIntegerField(default=30)
    include_tax_on_receipt = models.BooleanField(default=False)

    def __str__(self):
        return "Report settings"
