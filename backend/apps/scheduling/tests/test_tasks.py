"""
apps/scheduling/tests/test_tasks.py

Covers send_scheduled_email's success/retry/failure paths and
poll_due_scheduled_emails' due-row selection.
"""

from unittest.mock import patch

from django.core import mail
from django.test import TestCase
from django.utils import timezone

from apps.jobs.models import Job
from apps.scheduling.models import ScheduledEmail
from apps.scheduling.tasks import poll_due_scheduled_emails, send_scheduled_email
from apps.stats.models import Output
from apps.users.models import User


class SendScheduledEmailTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="jane@example.com", password="pass123", full_name="Jane Doe"
        )
        self.job = Job.objects.create(
            user=self.user, content="source", model="openai/gpt-4o", status="complete"
        )
        self.output = Output.objects.create(
            job=self.job, format="email", text="Newsletter body"
        )

    def _make_scheduled(self, **overrides):
        defaults = dict(
            output=self.output,
            user=self.user,
            recipients=["reader@example.com"],
            subject="Weekly update",
            edited_content="body",
            status="scheduled",
            scheduled_for=timezone.now() - timezone.timedelta(minutes=1),
        )
        defaults.update(overrides)
        return ScheduledEmail.objects.create(**defaults)

    def test_successful_send_marks_sent_and_notifies(self):
        scheduled = self._make_scheduled()
        send_scheduled_email(scheduled.id)
        scheduled.refresh_from_db()
        self.assertEqual(scheduled.status, "sent")
        self.assertIsNotNone(scheduled.sent_at)
        # newsletter send + confirmation email
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(mail.outbox[0].to, ["reader@example.com"])
        self.assertEqual(mail.outbox[1].to, [self.user.email])

    @patch("apps.scheduling.tasks.EmailMessage")
    def test_failed_send_increments_attempt_and_stays_scheduled_below_max(
        self, mock_email_message
    ):
        mock_email_message.return_value.send.side_effect = Exception("SMTP down")
        scheduled = self._make_scheduled()
        send_scheduled_email(scheduled.id)
        scheduled.refresh_from_db()
        self.assertEqual(scheduled.status, "scheduled")
        self.assertEqual(scheduled.attempt_count, 1)
        self.assertEqual(len(mail.outbox), 0)

    @patch("apps.scheduling.tasks.EmailMessage")
    def test_failed_send_marks_failed_after_max_attempts(self, mock_email_message):
        mock_email_message.return_value.send.side_effect = Exception("SMTP down")
        scheduled = self._make_scheduled(attempt_count=2)
        send_scheduled_email(scheduled.id)
        scheduled.refresh_from_db()
        self.assertEqual(scheduled.status, "failed")
        self.assertEqual(scheduled.error_message, "SMTP down")
        # confirmation-of-failure email only
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.user.email])

    def test_non_scheduled_status_is_skipped(self):
        scheduled = self._make_scheduled(status="cancelled")
        send_scheduled_email(scheduled.id)
        scheduled.refresh_from_db()
        self.assertEqual(scheduled.status, "cancelled")
        self.assertEqual(len(mail.outbox), 0)


class PollDueScheduledEmailsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="jane@example.com", password="pass123", full_name="Jane Doe"
        )
        self.job = Job.objects.create(
            user=self.user, content="source", model="openai/gpt-4o", status="complete"
        )
        self.output = Output.objects.create(
            job=self.job, format="email", text="body"
        )

    def test_only_due_scheduled_rows_are_sent(self):
        due = ScheduledEmail.objects.create(
            output=self.output,
            user=self.user,
            recipients=["a@example.com"],
            subject="due",
            edited_content="body",
            status="scheduled",
            scheduled_for=timezone.now() - timezone.timedelta(minutes=1),
        )
        not_due = ScheduledEmail.objects.create(
            output=self.output,
            user=self.user,
            recipients=["b@example.com"],
            subject="future",
            edited_content="body",
            status="scheduled",
            scheduled_for=timezone.now() + timezone.timedelta(hours=1),
        )

        poll_due_scheduled_emails()

        due.refresh_from_db()
        not_due.refresh_from_db()
        self.assertEqual(due.status, "sent")
        self.assertEqual(not_due.status, "scheduled")
