from django.db import models
from apps.users.models import User
import uuid
from django.conf import settings


# Create your models here.
class Job(models.Model):
    """
        Job model for storing the url of the websites and content of a website or blog and more for the project
    Args:
        models (Model): Stores the necessary field for performed by the context provided for the project
    """

    STATUS_CHOICES = [
        ("processing", "Processing"),
        ("complete", "Complete"),
        ("failed", "Failed"),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    content = models.TextField()
    formats = models.JSONField(default=list)
    source_url = models.URLField(null=True, blank=True, max_length=500)
    model = models.CharField(max_length=100)
    provider_used = models.CharField(max_length=20, default="", blank=True)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="processing"
    )
    word_count = models.IntegerField(default=0, null=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        self.word_count = len(self.content.split())
        super().save(*args, **kwargs)
