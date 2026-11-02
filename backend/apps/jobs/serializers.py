"""
Serializers for job creation, listing, detail, output rating, and scraping.

Design decisions:
    - JobCreateSerializer validates formats[] against model choices so invalid
      formats are rejected before the service layer runs.
    - JobListSerializer is intentionally lightweight — no outputs nested —
      to keep paginated list responses fast.
    - JobDetailSerializer nests OutputSerializer as a read-only many relation.
    - OutputRateSerializer uses only user_rating with an explicit IntegerField
      range validator; no other field is writable from this serializer.
    - ScrapeRequestSerializer uses URLField so Django validates URL structure
      before the scraper makes an external HTTP call.
    - ScrapeResponseSerializer is write-only from the view's perspective —
      it serializes the dict returned by fetch_from_url(), not a model instance.
"""

from rest_framework import serializers
from .models import Job
from apps.stats.models import Output


class OutputSerializer(serializers.ModelSerializer):
    """
    Full output representation including generation metrics
    Used nested inside JobDetailSerializer and standalone in OutputListView.
    """

    class Meta:
        model = Output
        fields = [
            "id",
            "job",
            "format",
            "text",
            "quality_score",
            "latency_ms",
            "tokens_generated",
            "tokens_per_second",
            "user_rating",
            "character_count",
            "created_at",
        ]
        read_only_fields = fields


class OutputRateSerializer(serializers.ModelSerializer):
    """
    Validates a star rating submission for a single output.
    Only user_rating is writable; all other fields are ignored.
    """

    user_rating = serializers.IntegerField(min_value=1, max_value=5)

    class Meta:
        model = Output
        fields = ["user_rating"]


class JobCreateSerializer(serializers.ModelSerializer):
    """
    Validates job creation input from the frontend.

    formats: list of one or more valid format choices.
    source_url: optional; when provided, scraper runs before repurposing.
    content: optional when source_url is provided; required otherwise.
    model: defaults to openrouter/auto if not specified.
    """

    content = serializers.CharField(required=False, allow_blank=True, max_length=50000)
    formats = serializers.MultipleChoiceField(
        choices=Output.FORMAT_CHOICES,
    )
    source_url = serializers.URLField(required=False, allow_blank=True)
    model = serializers.CharField(default="openrouter/free")

    class Meta:
        model = Job
        fields = [
            "id",
            "content",
            "formats",
            "model",
            "source_url",
        ]
        read_only_fields = ["id"]

    def validate(self, attrs):
        content = attrs.get("content")
        source_url = attrs.get("source_url")
        if not content and not source_url:
            raise serializers.ValidationError("Provide either content or source_url.")
        return attrs

    def create(self, validated_data):
        if "formats" in validated_data:
            validated_data["formats"] = list(validated_data["formats"])
        return super().create(validated_data)


class JobListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for paginated job list responses.
    Excludes outputs and content to keep payload small.
    """

    class Meta:
        model = Job
        fields = ["id", "status", "model", "word_count", "created_at"]
        read_only_fields = fields


class JobDetailSerializer(serializers.ModelSerializer):
    """
    Full job representation with nested outputs.
    Used after job creation and for GET /jobs/<id>/.
    """

    outputs = OutputSerializer(many=True, read_only=True)

    class Meta:
        model = Job
        fields = [
            "id",
            "status",
            "model",
            "source_url",
            "word_count",
            "formats",
            "outputs",
            "created_at",
        ]
        read_only_fields = fields


class ScrapeRequestSerializer(serializers.Serializer):
    """
    Validates the URL submitted to POST /api/v1/scrape/.
    URLField rejects malformed URLs before the scraper makes any HTTP call.
    """

    url = serializers.URLField()


class ScrapeResponseSerializer(serializers.Serializer):
    """
    Serializes the dict returned by fetch_from_url().
    Not tied to a model — fetch_from_url() returns a plain dict.
    """

    title = serializers.CharField(allow_blank=True)
    text = serializers.CharField()
    word_count = serializers.IntegerField()
