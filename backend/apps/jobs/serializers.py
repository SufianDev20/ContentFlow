import requests
from rest_framework import serializers

from .formats import FORMAT_CHOICES
from .models import Job, Output
from .services import llm, scraper


class OutputSerializer(serializers.ModelSerializer):
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
    user_rating = serializers.IntegerField(min_value=1, max_value=5)

    class Meta:
        model = Output
        fields = ["user_rating"]


class JobCreateSerializer(serializers.ModelSerializer):
    """`content` is optional when `source_url` is given: the page text is fetched into it."""

    content = serializers.CharField(
        required=False, allow_blank=True, max_length=scraper.MAX_CONTENT_LENGTH
    )
    formats = serializers.MultipleChoiceField(choices=FORMAT_CHOICES, allow_empty=False)
    source_url = serializers.URLField(required=False, allow_blank=True)
    model = serializers.CharField(default=llm.DEFAULT_MODEL)

    class Meta:
        model = Job
        fields = ["id", "content", "formats", "model", "source_url"]
        read_only_fields = ["id"]

    def validate(self, attrs):
        if not attrs.get("content"):
            source_url = attrs.get("source_url")
            if not source_url:
                raise serializers.ValidationError("Provide either content or source_url.")
            try:
                attrs["content"] = scraper.fetch_from_url(source_url)["text"]
            except (ValueError, requests.exceptions.RequestException) as exc:
                raise serializers.ValidationError({"source_url": str(exc)}) from exc
        return attrs

    def create(self, validated_data):
        requested = validated_data["formats"]
        validated_data["formats"] = [key for key, _ in FORMAT_CHOICES if key in requested]
        return super().create(validated_data)


class JobListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Job
        fields = ["id", "status", "model", "word_count", "created_at"]
        read_only_fields = fields


class JobDetailSerializer(serializers.ModelSerializer):
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
    url = serializers.URLField()


class ScrapeResponseSerializer(serializers.Serializer):
    title = serializers.CharField(allow_blank=True)
    text = serializers.CharField()
    word_count = serializers.IntegerField()
