import uuid
from django.conf import settings
from django.db import models

from apps.stats.models import Output


class ScheduledEmail(models.Model):
    """
    One scheduled/sent attempt to email an `email`-format Output to a
    recipient list at a future time. Separate from Output (rather than
    fields on it) because an output can be scheduled, cancelled, and
    rescheduled to different recipients multiple times.
    """

    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("scheduled", "Scheduled"),
        ("sent", "Sent"),
        ("failed", "Failed"),
        ("cancelled", "Cancelled"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    output = models.ForeignKey(
        Output, on_delete=models.CASCADE, related_name="scheduled_emails"
    )
    # Denormalized from output.job.user for cheap request.user-scoped queries
    # without a job__user join, matching the hard no-cross-user-access rule.
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    recipients = models.JSONField(default=list)
    subject = models.CharField(max_length=255)
    edited_content = models.TextField()

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")
    scheduled_for = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True, default="")
    attempt_count = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "scheduled_for"]),
        ]

    def __str__(self):
        return f"ScheduledEmail<{self.id}, {self.status}>"
