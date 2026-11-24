import uuid

from django.db import models
from django.utils import timezone

from apps.jobs.formats import FORMAT_CHOICES


class EvalArticle(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(unique=True, max_length=120)
    title = models.CharField(max_length=300)
    topic = models.CharField(max_length=100)
    source_text = models.TextField()
    key_facts = models.JSONField(help_text="List of verifiable factual claims from the article")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["topic", "slug"]

    def __str__(self):
        return f"{self.topic}: {self.title}"


class EvalRun(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending"
        RUNNING = "running"
        COMPLETE = "complete"
        FAILED = "failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    model = models.CharField(max_length=100)
    judge_model = models.CharField(max_length=100)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    total_outputs = models.IntegerField(default=0)
    passed_outputs = models.IntegerField(default=0)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"EvalRun {self.id} ({self.model}, {self.status})"

    @property
    def article_count(self):
        return self.results.values("article").distinct().count()

    @property
    def summary_line(self):
        return (
            f"{self.passed_outputs} of {self.total_outputs} outputs had no factual error "
            f"in my test set of {self.article_count} articles."
        )


class EvalResult(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run = models.ForeignKey(EvalRun, on_delete=models.CASCADE, related_name="results")
    article = models.ForeignKey(EvalArticle, on_delete=models.CASCADE, related_name="eval_results")
    format = models.CharField(max_length=30, choices=FORMAT_CHOICES)
    generated_text = models.TextField()
    generation_latency_ms = models.IntegerField(default=0)
    generation_provider = models.CharField(max_length=20, default="openrouter")

    claims_checked = models.JSONField(default=list)
    invented_facts = models.JSONField(default=list)
    factual_errors = models.IntegerField(default=0)
    passed = models.BooleanField(default=False)
    judge_raw_response = models.TextField(blank=True)

    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["run", "article", "format"]
        unique_together = [("run", "article", "format")]

    def __str__(self):
        status = "PASS" if self.passed else "FAIL"
        return f"{self.article.slug}/{self.format}: {status} ({self.factual_errors} errors)"
