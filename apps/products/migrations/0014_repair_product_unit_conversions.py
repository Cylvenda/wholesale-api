"""Repair corrupted ProductUnit conversion factors.

The shop had products whose base unit was a *pack* unit (e.g. "Crate ya soda"
with abbreviation ``CS``) and products that had a bottle unit and a crate unit
both configured with a conversion factor of ``1``.  Both make stock display and
sale validation wrong:

* base unit = crate  -> stock of 10121 is reported as 10121 crates;
* crate factor = 1  -> "1 CS = 1 CS" and selling 2 crates removes 2 bottles.

Repair rules (idempotent, historical SaleItem/PurchaseItem rows are untouched):

1. A product whose base unit is a crate-like pack while a bottle-like unit
   exists is switched to the bottle as its base unit.  The stored stock number
   is unchanged: it has always been counted in bottles.
2. The former base pack unit becomes a normal pack with its real size.
3. Any remaining non-base unit configured with a factor of 1 is set to the
   known pack size of that unit name.
4. Base abbreviations that clash with their pack unit get a distinct one.

Pack sizes are configured per unit name, never globally in application code.
"""

from django.db import migrations

# How many base units one of these packs holds.
PACK_SIZES = {
    "crate ya soda": 24,
    "chupa ya soda": 1,
    "crate ya bia": 24,
    "carton": 24,
}

# Unit names treated as "a pack of something", used by rule 1.
CRATE_NAMES = {"crate ya soda", "crate ya bia"}

# Unit names that can act as the bottle-level base unit, best first.
BOTTLE_NAMES = ("chupa ya soda", "bottle", "piece")

# Distinct abbreviation for a base unit that currently collides with a pack.
BASE_ABBREVIATIONS = {
    "chupa ya soda": "CHP",
}


def _normalise(name):
    return " ".join((name or "").strip().lower().split())


def repair(apps, schema_editor):
    Product = apps.get_model("products", "Product")
    ProductUnit = apps.get_model("products", "ProductUnit")
    Unit = apps.get_model("products", "Unit")

    for unit in Unit.objects.all():
        wanted = BASE_ABBREVIATIONS.get(_normalise(unit.name))
        if wanted and unit.abbreviation != wanted:
            Unit.objects.filter(pk=unit.pk).update(abbreviation=wanted)

    for product in Product.objects.all():
        base_unit = product.base_unit
        units = list(
            ProductUnit.objects.filter(product=product, is_active=True).select_related("unit")
        )

        # Rule 1: base unit is a crate but the shop also has a bottle unit.
        if _normalise(base_unit.name) in CRATE_NAMES:
            bottle = next(
                (
                    unit
                    for unit in Unit.objects.filter(is_active=True)
                    if _normalise(unit.name) in BOTTLE_NAMES and unit.pk != base_unit.pk
                ),
                None,
            )
            if bottle is not None:
                old_base_config = next(
                    (pu for pu in units if pu.unit_id == base_unit.pk), None
                )

                Product.objects.filter(pk=product.pk).update(base_unit=bottle)

                if not any(pu.unit_id == bottle.pk for pu in units):
                    ProductUnit.objects.create(
                        product=product,
                        unit=bottle,
                        conversion_factor=1,
                        buying_price=(
                            old_base_config.buying_price
                            if old_base_config
                            else product.buying_price
                        ),
                        selling_price=(
                            old_base_config.selling_price
                            if old_base_config
                            else product.selling_price
                        ),
                        is_active=True,
                        created_by_id=(
                            old_base_config.created_by_id
                            if old_base_config
                            else product.created_by_id
                        ),
                    )

        product.refresh_from_db()
        base_unit = product.base_unit

        for config in ProductUnit.objects.filter(product=product, is_active=True).select_related(
            "unit"
        ):
            if config.unit_id == base_unit.pk:
                if config.conversion_factor != 1:
                    ProductUnit.objects.filter(pk=config.pk).update(conversion_factor=1)
                continue

            # Rule 2/3: a non-base unit must hold more than one base unit.
            if int(config.conversion_factor) <= 1:
                pack_size = PACK_SIZES.get(_normalise(config.unit.name))
                if pack_size and pack_size > 1:
                    ProductUnit.objects.filter(pk=config.pk).update(
                        conversion_factor=pack_size
                    )


def noop(apps, schema_editor):
    """Historical installations keep their data untouched."""


class Migration(migrations.Migration):

    dependencies = [
        ("products", "0013_remove_productunit_allow_decimal_and_more"),
    ]

    operations = [
        migrations.RunPython(repair, noop),
    ]