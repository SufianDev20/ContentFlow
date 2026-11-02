"""
apps/scheduling/tests/test_views.py

Covers:
- POST /api/v1/scheduled-emails/
- GET  /api/v1/scheduled-emails/
- PATCH /api/v1/scheduled-emails/<uuid:pk>/
- POST /api/v1/scheduled-emails/<uuid:pk>/cancel/
- Cross-user access is rejected (hard scoping rule).
"""

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.jobs.models import Job
from apps.scheduling.models import ScheduledEmail
from apps.stats.models import Output
from apps.users.models import User


class ScheduledEmailViewTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="jane@example.com", password="pass123", full_name="Jane Doe"
        )
        self.other_user = User.objects.create_user(
            email="john@example.com", password="pass123", full_name="John Doe"
        )
        self.client.force_authenticate(user=self.user)

        self.job = Job.objects.create(
            user=self.user, content="source", model="openai/gpt-4o", status="complete"
        )
        self.email_output = Output.objects.create(
            job=self.job, format="email", text="Newsletter body"
        )
        self.tweet_output = Output.objects.create(
            job=self.job, format="tweet_thread", text="Tweet body"
        )

        self.list_create_url = reverse("scheduled-email-list-create")
        self.future_time = timezone.now() + timezone.timedelta(hours=1)

    def _create_payload(self, **overrides):
        payload = {
            "output": str(self.email_output.id),
            "recipients": ["reader@example.com"],
            "subject": "Weekly update",
            "scheduled_for": self.future_time.isoformat(),
        }
        payload.update(overrides)
        return payload

    def test_create_scheduled_email_returns_201(self):
        response = self.client.post(self.list_create_url, self._create_payload())
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(ScheduledEmail.objects.count(), 1)
        scheduled = ScheduledEmail.objects.first()
        self.assertEqual(scheduled.status, "scheduled")
        self.assertEqual(scheduled.edited_content, "Newsletter body")

    def test_create_rejects_non_email_format_output(self):
        payload = self._create_payload(output=str(self.tweet_output.id))
        response = self.client.post(self.list_create_url, payload)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_rejects_past_scheduled_for(self):
        past = timezone.now() - timezone.timedelta(hours=1)
        payload = self._create_payload(scheduled_for=past.isoformat())
        response = self.client.post(self.list_create_url, payload)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_rejects_other_users_output(self):
        other_job = Job.objects.create(
            user=self.other_user, content="x", model="openai/gpt-4o", status="complete"
        )
        other_output = Output.objects.create(
            job=other_job, format="email", text="Other body"
        )
        payload = self._create_payload(output=str(other_output.id))
        response = self.client.post(self.list_create_url, payload)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_list_scopes_to_request_user(self):
        ScheduledEmail.objects.create(
            output=self.email_output,
            user=self.user,
            recipients=["a@example.com"],
            subject="mine",
            edited_content="body",
            status="scheduled",
            scheduled_for=self.future_time,
        )
        other_job = Job.objects.create(
            user=self.other_user, content="x", model="openai/gpt-4o", status="complete"
        )
        other_output = Output.objects.create(
            job=other_job, format="email", text="body"
        )
        ScheduledEmail.objects.create(
            output=other_output,
            user=self.other_user,
            recipients=["b@example.com"],
            subject="theirs",
            edited_content="body",
            status="scheduled",
            scheduled_for=self.future_time,
        )

        response = self.client.get(self.list_create_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["subject"], "mine")

    def test_cancel_sets_status_cancelled(self):
        scheduled = ScheduledEmail.objects.create(
            output=self.email_output,
            user=self.user,
            recipients=["a@example.com"],
            subject="mine",
            edited_content="body",
            status="scheduled",
            scheduled_for=self.future_time,
        )
        url = reverse("scheduled-email-cancel", kwargs={"pk": scheduled.id})
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        scheduled.refresh_from_db()
        self.assertEqual(scheduled.status, "cancelled")

    def test_cancel_already_sent_returns_400(self):
        scheduled = ScheduledEmail.objects.create(
            output=self.email_output,
            user=self.user,
            recipients=["a@example.com"],
            subject="mine",
            edited_content="body",
            status="sent",
            scheduled_for=self.future_time,
            sent_at=timezone.now(),
        )
        url = reverse("scheduled-email-cancel", kwargs={"pk": scheduled.id})
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cancel_other_users_scheduled_email_returns_404(self):
        other_job = Job.objects.create(
            user=self.other_user, content="x", model="openai/gpt-4o", status="complete"
        )
        other_output = Output.objects.create(
            job=other_job, format="email", text="body"
        )
        scheduled = ScheduledEmail.objects.create(
            output=other_output,
            user=self.other_user,
            recipients=["b@example.com"],
            subject="theirs",
            edited_content="body",
            status="scheduled",
            scheduled_for=self.future_time,
        )
        url = reverse("scheduled-email-cancel", kwargs={"pk": scheduled.id})
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_update_content_before_send(self):
        scheduled = ScheduledEmail.objects.create(
            output=self.email_output,
            user=self.user,
            recipients=["a@example.com"],
            subject="mine",
            edited_content="body",
            status="scheduled",
            scheduled_for=self.future_time,
        )
        url = reverse("scheduled-email-update", kwargs={"pk": scheduled.id})
        response = self.client.patch(url, {"edited_content": "revised body"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        scheduled.refresh_from_db()
        self.assertEqual(scheduled.edited_content, "revised body")

    def test_update_after_sent_rejected(self):
        scheduled = ScheduledEmail.objects.create(
            output=self.email_output,
            user=self.user,
            recipients=["a@example.com"],
            subject="mine",
            edited_content="body",
            status="sent",
            scheduled_for=self.future_time,
            sent_at=timezone.now(),
        )
        url = reverse("scheduled-email-update", kwargs={"pk": scheduled.id})
        response = self.client.patch(url, {"edited_content": "revised body"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
