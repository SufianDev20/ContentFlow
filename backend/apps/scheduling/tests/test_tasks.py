from datetime import timedelta
from smtplib import SMTPException
from unittest.mock import patch

import pytest
from django.core import mail
from django.core.mail.backends import locmem
from django.utils import timezone

from apps.scheduling.models import ScheduledEmail
from apps.scheduling.tasks import MAX_ATTEMPTS, poll_due_scheduled_emails, send_scheduled_email

Status = ScheduledEmail.Status
READER = "reader@example.com"


@pytest.fixture
def make_scheduled(user, make_output):
    output = make_output(format="email", text="Newsletter body")

    def make(**overrides):
        fields = dict(
            output=output,
            user=user,
            recipients=[READER],
            subject="Weekly update",
            edited_content="edited body",
            status=Status.SCHEDULED,
            scheduled_for=timezone.now() - timedelta(minutes=1),
        )
        fields.update(overrides)
        return ScheduledEmail.objects.create(**fields)

    return make


@pytest.fixture
def smtp_down():
    """The newsletter's SMTP delivery fails; the owner's confirmation still goes out."""
    deliver = locmem.EmailBackend.send_messages

    def send_messages(self, messages):
        if any(READER in m.to for m in messages):
            raise SMTPException("SMTP down")
        return deliver(self, messages)

    with patch.object(locmem.EmailBackend, "send_messages", send_messages):
        yield


def sent_to(address):
    return [m for m in mail.outbox if address in m.to]


class TestSendScheduledEmail:
    def test_sends_the_edited_content_then_confirms_to_the_owner(self, make_scheduled, user):
        scheduled = make_scheduled()

        send_scheduled_email(scheduled.id)

        scheduled.refresh_from_db()
        assert scheduled.status == Status.SENT
        assert scheduled.sent_at is not None
        (newsletter,) = sent_to(READER)
        assert (newsletter.subject, newsletter.body) == ("Weekly update", "edited body")
        assert len(sent_to(user.email)) == 1

    def test_failure_below_the_attempt_limit_stays_scheduled_and_is_not_announced(
        self, make_scheduled, smtp_down, user
    ):
        scheduled = make_scheduled(attempt_count=MAX_ATTEMPTS - 2)

        send_scheduled_email(scheduled.id)

        scheduled.refresh_from_db()
        assert scheduled.status == Status.SCHEDULED
        assert scheduled.attempt_count == MAX_ATTEMPTS - 1
        assert mail.outbox == []

    def test_retry_that_succeeds_is_sent(self, make_scheduled):
        scheduled = make_scheduled(attempt_count=1)

        send_scheduled_email(scheduled.id)

        scheduled.refresh_from_db()
        assert scheduled.status == Status.SENT

    def test_failure_on_the_last_attempt_marks_failed_and_tells_the_owner(
        self, make_scheduled, smtp_down, user
    ):
        scheduled = make_scheduled(attempt_count=MAX_ATTEMPTS - 1)

        send_scheduled_email(scheduled.id)

        scheduled.refresh_from_db()
        assert scheduled.status == Status.FAILED
        assert scheduled.error_message == "SMTP down"
        (notice,) = mail.outbox
        assert notice.to == [user.email]
        assert "failed" in notice.subject

    @pytest.mark.parametrize("status", [Status.CANCELLED, Status.SENT, Status.FAILED, Status.DRAFT])
    def test_only_scheduled_rows_are_sent(self, make_scheduled, status):
        scheduled = make_scheduled(status=status)

        send_scheduled_email(scheduled.id)

        scheduled.refresh_from_db()
        assert scheduled.status == status
        assert mail.outbox == []

    def test_sending_twice_delivers_once(self, make_scheduled):
        scheduled = make_scheduled()

        send_scheduled_email(scheduled.id)
        send_scheduled_email(scheduled.id)

        assert len(sent_to(READER)) == 1

    def test_unknown_id_is_ignored(self, db):
        send_scheduled_email("00000000-0000-0000-0000-000000000000")

        assert mail.outbox == []


class TestPollDueScheduledEmails:
    def test_sends_only_due_scheduled_rows(self, make_scheduled):
        due = make_scheduled()
        future = make_scheduled(scheduled_for=timezone.now() + timedelta(hours=1))
        cancelled = make_scheduled(status=Status.CANCELLED)

        poll_due_scheduled_emails()

        for row, expected in [(due, Status.SENT), (future, Status.SCHEDULED), (cancelled, Status.CANCELLED)]:
            row.refresh_from_db()
            assert row.status == expected

    def test_one_failing_row_does_not_stop_the_rest(self, make_scheduled):
        first, second = make_scheduled(), make_scheduled()

        with patch(
            "apps.scheduling.tasks.send_scheduled_email",
            side_effect=[RuntimeError("boom"), None],
        ) as send:
            poll_due_scheduled_emails()

        assert send.call_count == 2
