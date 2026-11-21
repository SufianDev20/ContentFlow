"""Confirmation email to the account owner once a scheduled send has resolved."""

import logging
import time

from django.conf import settings
from django.core.mail import send_mail

from ..models import ScheduledEmail

logger = logging.getLogger(__name__)


def send_confirmation_email(scheduled_email):
    recipient_count = len(scheduled_email.recipients)

    if scheduled_email.status == ScheduledEmail.Status.SENT:
        subject = "Your scheduled email was sent"
        body = (
            f'Your email "{scheduled_email.subject}" was sent to '
            f"{recipient_count} recipient(s) at {scheduled_email.sent_at}."
        )
    else:
        subject = "Your scheduled email failed to send"
        body = (
            f'Your email "{scheduled_email.subject}" failed to send.\n\n'
            f"Error: {scheduled_email.error_message}\n\n"
            f"Job: /job/?id={scheduled_email.output.job_id}"
        )

    # Some SMTP sandboxes (Mailtrap) reject two mails within ~1s.
    time.sleep(settings.EMAIL_NOTIFICATION_DELAY_SECONDS)
    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[scheduled_email.user.email],
            fail_silently=False,
        )
    except Exception:
        # The ScheduledEmail row already records the real outcome.
        logger.exception(
            "Failed to send confirmation email for ScheduledEmail %s", scheduled_email.id
        )
