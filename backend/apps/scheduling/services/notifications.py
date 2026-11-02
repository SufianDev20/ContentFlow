"""
Confirmation email sent to the account owner after a scheduled send
resolves (success or failure). Never sent before the send attempt.
"""

import logging
import time

from django.core.mail import send_mail
from django.conf import settings

logger = logging.getLogger(__name__)


def send_confirmation_email(scheduled_email):
    recipient = scheduled_email.user.email
    recipient_count = len(scheduled_email.recipients)

    if scheduled_email.status == "sent":
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

    # ponytail: Mailtrap sandbox rejects 2 mails inside ~1s (550); drop when on a real SMTP provider.
    time.sleep(1.5)
    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient],
            fail_silently=False,
        )
    except Exception:
        # Notification failure must not fail the send task that called this —
        # the ScheduledEmail row already reflects the real outcome.
        logger.exception(
            "Failed to send confirmation email for ScheduledEmail %s", scheduled_email.id
        )
