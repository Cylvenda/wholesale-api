from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0003_user_is_active_alter_user_is_superuser")]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="role",
            field=models.CharField(
                choices=[
                    ("admin", "Admin"),
                    ("manager", "Manager"),
                    ("salesperson", "Salesperson"),
                    ("storekeeper", "Storekeeper"),
                    ("accountant", "Accountant"),
                ],
                default="salesperson",
                max_length=20,
            ),
        ),
    ]
