"""
Scheduled email dispatch. Called by apps/scheduling/scheduler.py's
periodic APScheduler job, every 60 seconds.
"""

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
            status="scheduled", scheduled_for__lte=timezone.now()
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
    should_notify = False

    with transaction.atomic():
        try:
            scheduled_email = ScheduledEmail.objects.select_for_update().get(
                pk=scheduled_email_id
            )
        except ScheduledEmail.DoesNotExist:
            return

        if scheduled_email.status != "scheduled":
            return

        try:
            message = EmailMessage(
                subject=scheduled_email.subject,
                body=scheduled_email.edited_content,
                to=scheduled_email.recipients,
            )
            message.send(fail_silently=False)
        except Exception as exc:
            scheduled_email.attempt_count += 1
            if scheduled_email.attempt_count < MAX_ATTEMPTS:
                scheduled_email.save(update_fields=["attempt_count", "updated_at"])
                return
            scheduled_email.status = "failed"
            scheduled_email.error_message = str(exc)
            scheduled_email.save(
                update_fields=["status", "error_message", "attempt_count", "updated_at"]
            )
            should_notify = True
        else:
            scheduled_email.status = "sent"
            scheduled_email.sent_at = timezone.now()
            scheduled_email.save(update_fields=["status", "sent_at", "updated_at"])
            should_notify = True

    if should_notify:
        send_confirmation_email(scheduled_email)
