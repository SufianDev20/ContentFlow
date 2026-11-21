import uuid

from django.conf import settings
from django.db import models

from .formats import FORMAT_CHOICES


class JobQuerySet(models.QuerySet):
    def for_user(self, user):
        return self.filter(user=user)


class OutputQuerySet(models.QuerySet):
    def for_user(self, user):
        return self.filter(job__user=user)


class Job(models.Model):
    class Status(models.TextChoices):
        PROCESSING = "processing", "Processing"
        COMPLETE = "complete", "Complete"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    content = models.TextField()
    formats = models.JSONField(default=list)
    source_url = models.URLField(null=True, blank=True, max_length=500)
    model = models.CharField(max_length=100)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PROCESSING
    )
    word_count = models.IntegerField(default=0, null=False)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = JobQuerySet.as_manager()

    def save(self, *args, **kwargs):
        self.word_count = len(self.content.split())
        super().save(*args, **kwargs)


class Output(models.Model):
    """One generated text for one requested format of a Job."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="outputs")
    format = models.CharField(max_length=30, choices=FORMAT_CHOICES)
    text = models.TextField()
    character_count = models.IntegerField(default=0)
    latency_ms = models.IntegerField(default=0)
    tokens_generated = models.IntegerField(default=0)
    tokens_per_second = models.FloatField(default=0.0)
    quality_score = models.IntegerField(default=0)
    user_rating = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    provider = models.CharField(max_length=20, default="openrouter")

    objects = OutputQuerySet.as_manager()

    def save(self, *args, **kwargs):
        self.character_count = len(self.text)
        super().save(*args, **kwargs)
