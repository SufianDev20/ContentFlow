"""Scheduled email dispatch, run every 60 seconds by scheduler.py."""

import logging

from django.core.mail import EmailMessage
from django.db import transaction
from django.utils import timezone

from .models import ScheduledEmail
from .services.notifications import send_confirmation_email

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3


def poll_due_scheduled_emails():
    due_ids = list(
        ScheduledEmail.objects.filter(
            status=ScheduledEmail.Status.SCHEDULED, scheduled_for__lte=timezone.now()
        ).values_list("id", flat=True)
    )
    for scheduled_email_id in due_ids:
        try:
            send_scheduled_email(scheduled_email_id)
        except Exception:
            logger.exception(
                "Unhandled error sending ScheduledEmail %s", scheduled_email_id
            )


def send_scheduled_email(scheduled_email_id):
    """
    Send one due email. The row is locked and its status re-checked so two
    scheduler processes can't both send it. A failed attempt is retried on
    the next poll until MAX_ATTEMPTS, then the email is marked failed.
    """
    with transaction.atomic():
        try:
            scheduled_email = ScheduledEmail.objects.select_for_update().get(
                pk=scheduled_email_id
            )
        except ScheduledEmail.DoesNotExist:
            return

        if scheduled_email.status != ScheduledEmail.Status.SCHEDULED:
            return

        try:
            EmailMessage(
                subject=scheduled_email.subject,
                body=scheduled_email.edited_content,
                to=scheduled_email.recipients,
            ).send(fail_silently=False)
        except Exception as exc:
            scheduled_email.attempt_count += 1
            if scheduled_email.attempt_count < MAX_ATTEMPTS:
                scheduled_email.save(update_fields=["attempt_count", "updated_at"])
                return
            scheduled_email.status = ScheduledEmail.Status.FAILED
            scheduled_email.error_message = str(exc)
            scheduled_email.save(
                update_fields=["status", "error_message", "attempt_count", "updated_at"]
            )
        else:
            scheduled_email.status = ScheduledEmail.Status.SENT
            scheduled_email.sent_at = timezone.now()
            scheduled_email.save(update_fields=["status", "sent_at", "updated_at"])

    send_confirmation_email(scheduled_email)
