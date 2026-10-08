from django.db import migrations

from apps.access_logs import triggers


class Migration(migrations.Migration):
    dependencies = [("access_logs", "0001_initial")]

    operations = [
        migrations.RunPython(triggers.apply_triggers, triggers.drop_triggers)
    ]