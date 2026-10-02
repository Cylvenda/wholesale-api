from django.db import migrations


def sync_staff_flag(apps, schema_editor):
    """Admins chosen through the user form were never flagged as staff.

    The form writes ``role="admin"`` but the permission checks read
    ``is_staff``, so those accounts were locked out of the very endpoints their
    role grants. Align the existing rows with the role they already hold.
    """
    User = apps.get_model("accounts", "User")
    User.objects.filter(role="admin").update(is_staff=True)
    User.objects.exclude(role="admin").update(is_staff=False)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0004_user_role_default"),
    ]

    operations = [
        migrations.RunPython(sync_staff_flag, noop),
    ]