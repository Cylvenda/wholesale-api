from django.db import migrations, models


def rename_default_business(apps, schema_editor):
    BusinessDetails = apps.get_model("reports", "BusinessDetails")
    BusinessDetails.objects.filter(name="CYL Stock").update(name="IMARA SHOP")


class Migration(migrations.Migration):
    dependencies = [
        ("reports", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="businessdetails",
            name="name",
            field=models.CharField(default="IMARA SHOP", max_length=150),
        ),
        migrations.RunPython(rename_default_business, migrations.RunPython.noop),
    ]
