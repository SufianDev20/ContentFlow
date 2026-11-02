from django.contrib import admin

from .models import ScheduledEmail


@admin.register(ScheduledEmail)
class ScheduledEmailAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "user",
        "status",
        "scheduled_for",
        "sent_at",
        "attempt_count",
        "created_at",
    ]
    list_filter = ["status"]
