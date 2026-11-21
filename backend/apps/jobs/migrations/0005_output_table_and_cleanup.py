from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("jobs", "0004_adopt_output"),
        ("stats", "0004_output_moved_to_jobs"),
    ]

    operations = [
        migrations.AlterModelTable(name="output", table=None),
        migrations.RemoveField(model_name="job", name="provider_used"),
    ]
