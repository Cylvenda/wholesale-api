from config.models import BaseModel
from django.db import models

class Category(BaseModel):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name

class Brand(BaseModel):
    name = models.CharField(max_length=100, unique=True)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="brands" )

    def __str__(self):
        return self.name

class Unit(BaseModel):
    name = models.CharField(max_length=50, unique=True)
    quantity = models.PositiveIntegerField(default=0)
    abbreviation = models.CharField(max_length=10, blank=True, null=True)

    def __str__(self):
        return self.name

class Product(BaseModel):
    brand = models.ForeignKey(Brand, on_delete=models.PROTECT, related_name="products" )
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name="products")
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    buying_price = models.DecimalField(max_digits=12, decimal_places=2)
    selling_price = models.DecimalField(max_digits=12, decimal_places=2)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name

# class ProductVariant(BaseModel):
#     product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="variants")
#     name = models.CharField(max_length=100)
#     unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name="variants")
#     quantity_per_unit = models.PositiveIntegerField(default=1)
#     buying_price = models.DecimalField(max_digits=12, decimal_places=2)
#     selling_price = models.DecimalField(max_digits=12, decimal_places=2)
#     is_active = models.BooleanField(default=True)
#
#     def __str__(self):
#         return f"{self.product.name} - {self.name}"
