import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("jobs", "0004_adopt_output"),
        ("scheduling", "0001_initial"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name="scheduledemail",
                    name="output",
                    field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="scheduled_emails", to="jobs.output"),
                ),
            ],
            database_operations=[],
        ),
    ]
