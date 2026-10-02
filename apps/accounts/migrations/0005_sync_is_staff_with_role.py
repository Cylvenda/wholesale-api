from django.db import migrations

# Older installs stored the owner as "Super Admin", which is not one of the
# Roles choices. It behaved as an admin everywhere except this sync.
LEGACY_ADMIN_ROLES = ("Super Admin",)


def sync_staff_flag(apps, schema_editor):
    """Align ``is_staff`` with the role, without ever demoting a superuser.

    The user form writes ``role="admin"`` but the permission checks read
    ``is_staff``, so accounts promoted through the form were locked out of the
    endpoints their own role grants.

    A superuser keeps staff access unconditionally: Django's own
    ``createsuperuser`` grants ``is_staff`` without touching ``role``, and
    demoting one would lock the shop owner out of their own shop.
    """
    User = apps.get_model("accounts", "User")

    # Older installs stored the owner as "Super Admin", which is not one of the
    # Roles choices. Normalise it so the role is something the app understands.
    User.objects.filter(role__in=LEGACY_ADMIN_ROLES).update(role="admin")

    User.objects.filter(is_superuser=True).update(is_staff=True)
    User.objects.filter(is_superuser=False, role="admin").update(is_staff=True)
    User.objects.exclude(
        is_superuser=True
    ).exclude(role="admin").update(is_staff=False)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0004_user_role_default"),
    ]

    operations = [
        migrations.RunPython(sync_staff_flag, noop),
    ]