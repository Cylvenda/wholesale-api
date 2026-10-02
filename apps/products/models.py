from config.models import BaseModel
from django.core.validators import MinValueValidator
from django.db import models


class Category(BaseModel):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name


class Brand(BaseModel):
    name = models.CharField(max_length=100, unique=True)
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="brands"
    )

    def __str__(self):
        return self.name


class Unit(BaseModel):
    name = models.CharField(max_length=50, unique=True)
    abbreviation = models.CharField(max_length=10, blank=True, null=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


def format_unit(unit) -> str:
    return f"{unit.name} ({unit.abbreviation})" if unit.abbreviation else unit.name


class Product(BaseModel):
    brand = models.ForeignKey(Brand, on_delete=models.PROTECT, related_name="products")
    base_unit = models.ForeignKey(
        Unit, on_delete=models.PROTECT, related_name="base_products"
    )
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    buying_price = models.DecimalField(max_digits=12, decimal_places=2)
    selling_price = models.DecimalField(max_digits=12, decimal_places=2)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class ProductUnit(BaseModel):
    """A unit this product can be bought or sold in.

    ``conversion_factor`` answers "how many base units are inside one of this
    unit?".  It is a whole number: this shop never trades fractional units.
    """

    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="product_units"
    )
    unit = models.ForeignKey(
        Unit, on_delete=models.PROTECT, related_name="product_units"
    )
    conversion_factor = models.PositiveIntegerField(
        default=1, validators=[MinValueValidator(1)]
    )
    buying_price = models.DecimalField(max_digits=12, decimal_places=2)
    selling_price = models.DecimalField(max_digits=12, decimal_places=2)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["product", "unit"],
                name="unique_product_unit",
            )
        ]
        ordering = ["conversion_factor"]

    def __str__(self):
        return f"{self.product.name} - {self.unit.name} (x{self.conversion_factor})"

    @property
    def is_base_unit(self) -> bool:
        return self.unit_id == self.product.base_unit_id

    @property
    def unit_label(self) -> str:
        return format_unit(self.unit)

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.conversion_factor < 1:
            raise ValidationError(
                "Conversion factor must be a whole number of at least 1."
            )
        if self.product_id and self.unit_id and self.is_base_unit:
            if self.conversion_factor != 1:
                raise ValidationError(
                    "Base unit must have conversion factor of 1."
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)