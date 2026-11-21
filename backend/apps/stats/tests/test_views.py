from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.scheduling.models import ScheduledEmail


@pytest.mark.parametrize("name", ["stats-models", "stats-summary", "stats-scheduling"])
def test_stats_require_authentication(client, name):
    assert client.get(reverse(name)).status_code == 401


class TestModelStats:
    url = reverse("stats-models")

    def test_empty_without_outputs(self, api):
        assert api.get(self.url).data == []

    def test_aggregates_per_model_and_format_for_own_outputs_only(
        self, api, make_job, make_output, other_user
    ):
        fast = make_job(model="model-a")
        make_output(job=fast, format="email", quality_score=60, latency_ms=100, user_rating=4)
        make_output(job=fast, format="email", quality_score=80, latency_ms=300, user_rating=5)
        make_output(job=fast, format="tldr", quality_score=90)
        make_output(job=make_job(model="model-b"), format="email", quality_score=10)
        make_output(job=make_job(owner=other_user, model="model-a"), format="email", quality_score=0)

        rows = {(r["model"], r["format"]): r for r in api.get(self.url).data}

        assert set(rows) == {("model-a", "email"), ("model-a", "tldr"), ("model-b", "email")}
        email = rows[("model-a", "email")]
        assert email["total_generations"] == 2
        assert email["avg_quality_score"] == 70
        assert email["avg_latency_ms"] == 200
        assert email["avg_user_rating"] == 4.5
        assert rows[("model-a", "tldr")]["avg_user_rating"] is None


class TestSummary:
    url = reverse("stats-summary")

    def test_zero_values_without_data(self, api):
        assert api.get(self.url).data == {
            "total_jobs": 0,
            "total_outputs": 0,
            "best_model_overall": None,
            "avg_quality_score": 0,
        }

    def test_counts_own_data_and_picks_the_best_model_by_average_quality(
        self, api, make_job, make_output, other_user
    ):
        good, poor = make_job(model="good"), make_job(model="poor")
        make_output(job=good, quality_score=90)
        make_output(job=good, quality_score=70)
        make_output(job=poor, quality_score=40)
        make_job(model="idle")
        make_output(job=make_job(owner=other_user, model="theirs"), quality_score=100)

        data = api.get(self.url).data

        assert data["total_jobs"] == 3
        assert data["total_outputs"] == 3
        assert data["best_model_overall"] == "good"
        assert data["avg_quality_score"] == 66.7


class TestSchedulingStats:
    url = reverse("stats-scheduling")

    def schedule(self, user, output, status, days_ago=0):
        row = ScheduledEmail.objects.create(
            output=output, user=user, recipients=["a@example.com"], subject="s",
            edited_content="b", status=status,
        )
        ScheduledEmail.objects.filter(pk=row.pk).update(created_at=timezone.now() - timedelta(days=days_ago))

    def test_counts_every_status_and_daily_activity_for_own_emails_only(
        self, api, user, other_user, make_output, make_job
    ):
        output = make_output()
        Status = ScheduledEmail.Status
        self.schedule(user, output, Status.SENT)
        self.schedule(user, output, Status.SENT)
        self.schedule(user, output, Status.FAILED, days_ago=1)
        self.schedule(other_user, make_output(job=make_job(owner=other_user)), Status.SENT)

        data = api.get(self.url).data

        assert data["status_counts"] == {
            "draft": 0, "scheduled": 0, "sent": 2, "failed": 1, "cancelled": 0,
        }
        assert [(d["scheduled_count"], d["sent_count"]) for d in data["activity"]] == [(1, 0), (2, 2)]
