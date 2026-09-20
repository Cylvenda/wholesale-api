from django.db import models

from config.models import BaseModel


class Customer(BaseModel):
    name = models.CharField(max_length=150)
    phone = models.CharField(max_length=30, blank=True, null=True)
    email = models.EmailField(blank=True)
    business_location = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name
