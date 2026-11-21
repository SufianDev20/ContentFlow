"""
Output moved from apps.stats to apps.jobs (it is Job's child, and stats only
aggregates it). The table is untouched here; 0005 renames it.
"""

import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("jobs", "0003_job_provider_used"),
        ("stats", "0003_output_provider"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="Output",
                    fields=[
                        ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ("format", models.CharField(choices=[("tweet_thread", "Tweet Thread"), ("linkedin", "LinkedIn"), ("email", "Email"), ("tldr", "TL;DR")], max_length=30)),
                        ("text", models.TextField()),
                        ("character_count", models.IntegerField(default=0)),
                        ("latency_ms", models.IntegerField(default=0)),
                        ("tokens_generated", models.IntegerField(default=0)),
                        ("tokens_per_second", models.FloatField(default=0.0)),
                        ("quality_score", models.IntegerField(default=0)),
                        ("user_rating", models.IntegerField(blank=True, null=True)),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("provider", models.CharField(default="openrouter", max_length=20)),
                        ("job", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="outputs", to="jobs.job")),
                    ],
                    options={"db_table": "stats_output"},
                ),
            ],
            database_operations=[],
        ),
    ]
