"""
apps/stats/tests/test_views.py

Covers GET /api/v1/stats/models/ and GET /api/v1/stats/summary/ per PRD 7.5.
Output lives in apps.stats.models. Job lives in apps.jobs.models.
"""

from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from apps.users.models import User
from apps.jobs.models import Job
from apps.stats.models import Output


class ModelStatsViewTests(APITestCase):
    def setUp(self):
        self.url = reverse("stats-models")
        self.user = User.objects.create_user(
            email="jane@example.com", password="pass123", full_name="Jane Doe"
        )
        self.other_user = User.objects.create_user(
            email="bob@example.com", password="pass123", full_name="Bob Smith"
        )
        self.client.force_authenticate(user=self.user)

    def test_without_authentication_returns_401(self):
        self.client.force_authenticate(user=None)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_with_no_outputs_returns_empty_list(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])

    def test_groups_by_model_and_format(self):
        job = Job.objects.create(
            user=self.user, content="a", model="openai/gpt-4o", status="complete"
        )
        Output.objects.create(
            job=job, format="tweet_thread", text="x", quality_score=80, latency_ms=1000
        )
        Output.objects.create(
            job=job, format="tweet_thread", text="y", quality_score=90, latency_ms=2000
        )
        Output.objects.create(
            job=job, format="linkedin", text="z", quality_score=70, latency_ms=1500
        )

        response = self.client.get(self.url)
        self.assertEqual(len(response.data), 2)

        tweet_row = next(r for r in response.data if r["format"] == "tweet_thread")
        self.assertEqual(tweet_row["total_generations"], 2)
        self.assertEqual(tweet_row["avg_quality_score"], 85.0)

    def test_excludes_other_users_outputs(self):
        other_job = Job.objects.create(
            user=self.other_user, content="a", model="claude/opus", status="complete"
        )
        Output.objects.create(job=other_job, format="email", text="x", quality_score=90)
        response = self.client.get(self.url)
        self.assertEqual(response.data, [])

    def test_avg_user_rating_is_null_when_no_ratings_given(self):
        job = Job.objects.create(
            user=self.user, content="a", model="openai/gpt-4o", status="complete"
        )
        Output.objects.create(job=job, format="email", text="x", quality_score=80)
        response = self.client.get(self.url)
        self.assertIsNone(response.data[0]["avg_user_rating"])

    def test_avg_user_rating_computed_when_ratings_present(self):
        job = Job.objects.create(
            user=self.user, content="a", model="openai/gpt-4o", status="complete"
        )
        Output.objects.create(
            job=job, format="email", text="x", quality_score=80, user_rating=4
        )
        Output.objects.create(
            job=job, format="email", text="y", quality_score=80, user_rating=2
        )
        response = self.client.get(self.url)
        self.assertEqual(response.data[0]["avg_user_rating"], 3.0)


class SummaryStatsViewTests(APITestCase):
    def setUp(self):
        self.url = reverse("stats-summary")
        self.user = User.objects.create_user(
            email="jane@example.com", password="pass123", full_name="Jane Doe"
        )
        self.other_user = User.objects.create_user(
            email="bob@example.com", password="pass123", full_name="Bob Smith"
        )
        self.client.force_authenticate(user=self.user)

    def test_without_authentication_returns_401(self):
        self.client.force_authenticate(user=None)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_with_no_jobs_returns_zero_values(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total_jobs"], 0)
        self.assertEqual(response.data["total_outputs"], 0)
        self.assertIsNone(response.data["best_model_overall"])
        self.assertEqual(response.data["avg_quality_score"], 0)

    def test_counts_only_own_jobs_and_outputs(self):
        job = Job.objects.create(
            user=self.user, content="a", model="openai/gpt-4o", status="complete"
        )
        Output.objects.create(job=job, format="email", text="x", quality_score=80)

        other_job = Job.objects.create(
            user=self.other_user, content="b", model="claude/opus", status="complete"
        )
        Output.objects.create(job=other_job, format="email", text="y", quality_score=95)

        response = self.client.get(self.url)
        self.assertEqual(response.data["total_jobs"], 1)
        self.assertEqual(response.data["total_outputs"], 1)

    def test_best_model_overall_picks_highest_avg_quality(self):
        job_gpt = Job.objects.create(
            user=self.user, content="a", model="openai/gpt-4o", status="complete"
        )
        job_claude = Job.objects.create(
            user=self.user, content="b", model="claude/opus", status="complete"
        )
        Output.objects.create(job=job_gpt, format="email", text="x", quality_score=70)
        Output.objects.create(
            job=job_claude, format="email", text="y", quality_score=95
        )

        response = self.client.get(self.url)
        self.assertEqual(response.data["best_model_overall"], "claude/opus")

    def test_avg_quality_score_is_overall_average_across_models(self):
        job = Job.objects.create(
            user=self.user, content="a", model="openai/gpt-4o", status="complete"
        )
        Output.objects.create(job=job, format="email", text="x", quality_score=80)
        Output.objects.create(job=job, format="linkedin", text="y", quality_score=90)

        response = self.client.get(self.url)
        self.assertEqual(response.data["avg_quality_score"], 85.0)
