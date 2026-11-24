from django.contrib import admin

from .models import EvalArticle, EvalRun, EvalResult


@admin.register(EvalArticle)
class EvalArticleAdmin(admin.ModelAdmin):
    list_display = ["slug", "title", "topic", "fact_count", "created_at"]
    list_filter = ["topic"]
    search_fields = ["title", "slug"]

    @admin.display(description="Facts")
    def fact_count(self, obj):
        return len(obj.key_facts) if obj.key_facts else 0


@admin.register(EvalRun)
class EvalRunAdmin(admin.ModelAdmin):
    list_display = ["id", "model", "judge_model", "status", "total_outputs", "passed_outputs", "created_at"]
    list_filter = ["status", "model"]


@admin.register(EvalResult)
class EvalResultAdmin(admin.ModelAdmin):
    list_display = ["id", "run", "article", "format", "factual_errors", "passed", "created_at"]
    list_filter = ["passed", "format"]
    raw_id_fields = ["run", "article"]
