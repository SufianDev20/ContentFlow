from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("jobs", "0004_adopt_output"),
        ("scheduling", "0002_output_in_jobs_app"),
        ("stats", "0003_output_provider"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[migrations.DeleteModel(name="Output")],
            database_operations=[],
        ),
    ]
