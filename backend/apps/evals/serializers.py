from rest_framework import serializers

from .models import EvalArticle, EvalRun, EvalResult


class EvalArticleSerializer(serializers.ModelSerializer):
    fact_count = serializers.SerializerMethodField()
    word_count = serializers.SerializerMethodField()

    class Meta:
        model = EvalArticle
        fields = ["id", "slug", "title", "topic", "fact_count", "word_count", "created_at"]

    def get_fact_count(self, obj):
        return len(obj.key_facts) if obj.key_facts else 0

    def get_word_count(self, obj):
        return len(obj.source_text.split()) if obj.source_text else 0


class EvalResultSerializer(serializers.ModelSerializer):
    article_slug = serializers.CharField(source="article.slug", read_only=True)
    article_title = serializers.CharField(source="article.title", read_only=True)

    class Meta:
        model = EvalResult
        fields = [
            "id", "article_slug", "article_title", "format",
            "factual_errors", "passed", "claims_checked", "invented_facts",
            "generation_latency_ms", "generation_provider", "created_at",
        ]


class EvalRunListSerializer(serializers.ModelSerializer):
    summary_line = serializers.CharField(read_only=True)

    class Meta:
        model = EvalRun
        fields = [
            "id", "model", "judge_model", "status",
            "total_outputs", "passed_outputs",
            "started_at", "completed_at", "created_at", "summary_line",
        ]


class EvalRunDetailSerializer(serializers.ModelSerializer):
    results = EvalResultSerializer(many=True, read_only=True)
    summary_line = serializers.CharField(read_only=True)

    class Meta:
        model = EvalRun
        fields = [
            "id", "model", "judge_model", "status",
            "total_outputs", "passed_outputs",
            "started_at", "completed_at", "created_at",
            "summary_line", "results",
        ]
