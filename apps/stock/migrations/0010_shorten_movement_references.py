import re
from uuid import UUID

from django.db import migrations

UUID_PATTERN = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)


def shorten_movement_references(apps, schema_editor):
    StockMovement = apps.get_model("stock", "StockMovement")
    Purchase = apps.get_model("purchases", "Purchase")
    Sale = apps.get_model("sales", "Sale")

    purchase_codes = {
        str(purchase_uuid): f"PUR-{purchase_id:06d}"
        for purchase_id, purchase_uuid in Purchase.objects.values_list("pk", "uuid")
    }
    sale_codes = {
        str(sale_uuid): f"SAL-{sale_id:06d}"
        for sale_id, sale_uuid in Sale.objects.values_list("pk", "uuid")
    }

    for movement in StockMovement.objects.exclude(reference="").iterator():
        raw_reference = str(movement.reference)
        try:
            normalized_uuid = str(UUID(raw_reference))
        except (ValueError, TypeError, AttributeError):
            continue

        movement_type = movement.movement_type.lower()
        if "purchase" in movement_type:
            code = purchase_codes.get(normalized_uuid)
        elif "sale" in movement_type:
            code = sale_codes.get(normalized_uuid)
        else:
            code = purchase_codes.get(normalized_uuid) or sale_codes.get(
                normalized_uuid
            )

        code = code or f"MOV-{UUID(raw_reference).hex[:8].upper()}"
        notes = re.sub(
            re.escape(raw_reference), code, movement.notes or "", flags=re.IGNORECASE
        )
        notes = UUID_PATTERN.sub("related item", notes)
        movement.reference = code
        movement.notes = notes
        movement.save(update_fields=["reference", "notes"])


class Migration(migrations.Migration):
    dependencies = [
        ("stock", "0009_alter_stockmovement_movement_type"),
        ("purchases", "0007_alter_purchase_status"),
        ("sales", "0007_alter_sale_payment_status"),
    ]

    operations = [
        migrations.RunPython(shorten_movement_references, migrations.RunPython.noop),
    ]
