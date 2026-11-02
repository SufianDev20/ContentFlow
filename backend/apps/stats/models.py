from django.db import models
from apps.jobs.models import Job
import uuid


# Create your models here.
class Output(models.Model):
    """
      Output generated via the LLM
    Args:
        models (Model): stores the output generated
    """

    FORMAT_CHOICES = [
        ("tweet_thread", "Tweet Thread"),
        ("linkedin", "LinkedIn"),
        ("email", "Email"),
        ("tldr", "TL;DR"),
    ]
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

    def save(self, *args, **kwargs):
        self.character_count = len(self.text)
        super().save(*args, **kwargs)
