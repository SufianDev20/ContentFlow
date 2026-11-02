"""
apps/jobs/tests/test_views.py

Test cases for job and output endpoints:
- POST /api/v1/jobs/
- GET  /api/v1/jobs/
- GET  /api/v1/jobs/<uuid:pk>/
- GET  /api/v1/jobs/outputs/  (OutputListView)
- POST /api/v1/jobs/outputs/<uuid:pk>/rate/  (adjust to your actual rate endpoint)

Mocks the LLM call and scraper so tests don't hit external services.
Adjust URL names and mock targets to match your actual code paths.
"""

from unittest.mock import patch
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from apps.users.models import User
from apps.jobs.models import Job
from apps.stats.models import Output


class JobCreateViewTests(APITestCase):
    def setUp(self):
        self.url = reverse("job-list")  # adjust name
        self.user = User.objects.create_user(
            email="jane@example.com", password="pass123", full_name="Jane Doe"
        )
        self.client.force_authenticate(user=self.user)

    @patch("apps.jobs.services.call_llm")
    def test_create_job_with_valid_data_returns_201(self, mock_llm):
        mock_llm.return_value = {"text": "generated content", "tokens_generated": 100}
        payload = {
            "content": "Some source content to repurpose.",
            "formats": ["tweet_thread", "linkedin"],
            "model": "openai/gpt-4o",
        }
        response = self.client.post(self.url, payload)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Job.objects.count(), 1)

    def test_create_job_without_authentication_returns_401(self):
        self.client.force_authenticate(user=None)
        payload = {"content": "text", "formats": ["email"], "model": "openai/gpt-4o"}
        response = self.client.post(self.url, payload)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_create_job_without_content_fails(self):
        payload = {"formats": ["email"], "model": "openai/gpt-4o"}
        response = self.client.post(self.url, payload)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_job_with_invalid_format_choice_fails(self):
        payload = {
            "content": "Some content.",
            "formats": ["not_a_real_format"],
            "model": "openai/gpt-4o",
        }
        response = self.client.post(self.url, payload)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_job_assigns_job_to_authenticated_user(self):
        with patch("apps.jobs.services.call_llm") as mock_llm:
            mock_llm.return_value = {"text": "output", "tokens_generated": 50}
            payload = {
                "content": "Some content here.",
                "formats": ["email"],
                "model": "openai/gpt-4o",
            }
            self.client.post(self.url, payload)
        job = Job.objects.first()
        self.assertEqual(job.user, self.user)

    def test_create_job_computes_word_count(self):
        with patch("apps.jobs.services.call_llm") as mock_llm:
            mock_llm.return_value = {"text": "output", "tokens_generated": 50}
            payload = {
                "content": "one two three four five",
                "formats": ["email"],
                "model": "openai/gpt-4o",
            }
            self.client.post(self.url, payload)
        job = Job.objects.first()
        self.assertEqual(job.word_count, 5)


class JobListViewTests(APITestCase):
    def setUp(self):
        self.url = reverse("job-list")
        self.user = User.objects.create_user(
            email="jane@example.com", password="pass123", full_name="Jane Doe"
        )
        self.other_user = User.objects.create_user(
            email="bob@example.com", password="pass123", full_name="Bob Smith"
        )
        self.client.force_authenticate(user=self.user)

    def test_list_returns_only_own_jobs(self):
        Job.objects.create(
            user=self.user, content="a", model="gpt-4o", status="complete"
        )
        Job.objects.create(
            user=self.other_user, content="b", model="gpt-4o", status="complete"
        )
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("results", response.data)
        self.assertEqual(len(results), 1)

    def test_list_without_authentication_returns_401(self):
        self.client.force_authenticate(user=None)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_list_excludes_output_details(self):
        Job.objects.create(
            user=self.user, content="a", model="gpt-4o", status="complete"
        )
        response = self.client.get(self.url)
        results = response.data.get("results", response.data)
        self.assertNotIn("outputs", results[0])

    def test_list_is_paginated(self):
        for i in range(15):
            Job.objects.create(
                user=self.user,
                content=f"content {i}",
                model="gpt-4o",
                status="complete",
            )
        response = self.client.get(self.url)
        self.assertIn("results", response.data)
        self.assertIn("count", response.data)


class JobDetailViewTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="jane@example.com", password="pass123", full_name="Jane Doe"
        )
        self.other_user = User.objects.create_user(
            email="bob@example.com", password="pass123", full_name="Bob Smith"
        )
        self.job = Job.objects.create(
            user=self.user, content="a", model="gpt-4o", status="complete"
        )
        self.client.force_authenticate(user=self.user)

    def test_detail_returns_job_with_nested_outputs(self):
        Output.objects.create(job=self.job, format="email", text="output text")
        url = reverse("job-detail", args=[self.job.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("outputs", response.data)
        self.assertEqual(len(response.data["outputs"]), 1)

    def test_detail_for_other_users_job_returns_404(self):
        self.client.force_authenticate(user=self.other_user)
        url = reverse("job-detail", args=[self.job.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_detail_for_nonexistent_job_returns_404(self):
        url = reverse("job-detail", args=["00000000-0000-0000-0000-000000000000"])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class OutputListViewTests(APITestCase):
    def setUp(self):
        self.url = reverse("output-list")  # adjust name
        self.user = User.objects.create_user(
            email="jane@example.com", password="pass123", full_name="Jane Doe"
        )
        self.other_user = User.objects.create_user(
            email="bob@example.com", password="pass123", full_name="Bob Smith"
        )
        self.job = Job.objects.create(
            user=self.user, content="a", model="openai/gpt-4o", status="complete"
        )
        self.other_job = Job.objects.create(
            user=self.other_user, content="b", model="claude/opus", status="complete"
        )
        self.client.force_authenticate(user=self.user)

    def test_list_returns_only_own_outputs(self):
        Output.objects.create(job=self.job, format="email", text="mine")
        Output.objects.create(job=self.other_job, format="email", text="not mine")
        response = self.client.get(self.url)
        results = response.data.get("results", response.data)
        self.assertEqual(len(results), 1)

    def test_list_without_authentication_returns_401(self):
        self.client.force_authenticate(user=None)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_filter_by_format_returns_matching_only(self):
        Output.objects.create(job=self.job, format="email", text="a")
        Output.objects.create(job=self.job, format="tweet_thread", text="b")
        response = self.client.get(self.url, {"format": "email"})
        results = response.data.get("results", response.data)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["format"], "email")

    def test_filter_by_model_returns_matching_only(self):
        job_gpt = Job.objects.create(
            user=self.user, content="a", model="openai/gpt-4o", status="complete"
        )
        job_claude = Job.objects.create(
            user=self.user, content="b", model="claude/opus", status="complete"
        )
        Output.objects.create(job=job_gpt, format="email", text="a")
        Output.objects.create(job=job_claude, format="email", text="b")
        response = self.client.get(self.url, {"model": "claude/opus"})
        results = response.data.get("results", response.data)
        self.assertEqual(len(results), 1)

    def test_combined_filters_apply_together(self):
        job_gpt = Job.objects.create(
            user=self.user, content="a", model="openai/gpt-4o", status="complete"
        )
        Output.objects.create(job=job_gpt, format="tweet_thread", text="a")
        Output.objects.create(job=job_gpt, format="email", text="b")
        response = self.client.get(
            self.url, {"format": "email", "model": "openai/gpt-4o"}
        )
        results = response.data.get("results", response.data)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["format"], "email")

    def test_results_ordered_newest_first(self):
        first = Output.objects.create(job=self.job, format="email", text="first")
        second = Output.objects.create(job=self.job, format="email", text="second")
        response = self.client.get(self.url)
        results = response.data.get("results", response.data)
        self.assertEqual(results[0]["id"], str(second.id))


class OutputRateViewTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="jane@example.com", password="pass123", full_name="Jane Doe"
        )
        self.other_user = User.objects.create_user(
            email="bob@example.com", password="pass123", full_name="Bob Smith"
        )
        self.job = Job.objects.create(
            user=self.user, content="a", model="gpt-4o", status="complete"
        )
        self.output = Output.objects.create(
            job=self.job, format="email", text="content"
        )
        self.client.force_authenticate(user=self.user)

    def test_rate_with_valid_score_updates_output(self):
        url = reverse("output-rate", args=[self.output.id])  # adjust name
        response = self.client.patch(url, {"user_rating": 4})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.output.refresh_from_db()
        self.assertEqual(self.output.user_rating, 4)

    def test_rate_with_score_above_5_fails(self):
        url = reverse("output-rate", args=[self.output.id])
        response = self.client.patch(url, {"user_rating": 6})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_rate_with_score_below_1_fails(self):
        url = reverse("output-rate", args=[self.output.id])
        response = self.client.patch(url, {"user_rating": 0})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_rate_other_users_output_returns_404(self):
        self.client.force_authenticate(user=self.other_user)
        url = reverse("output-rate", args=[self.output.id])
        response = self.client.patch(url, {"user_rating": 3})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
