from django.contrib import admin
from .models import Job
from apps.stats.models import Output


# Register your models here.
@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "model", "status", "word_count", "created_at"]


@admin.register(Output)
class OutputAdmin(admin.ModelAdmin):

    list_display = ["id", "job", "format", "quality_score", "user_rating", "created_at"]
