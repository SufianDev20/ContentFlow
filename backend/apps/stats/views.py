"""
apps/stats/views.py

Two read-only endpoints. No models in this app.
Output now lives in apps.stats.models per your Option B decision.
Job stays in apps.jobs.models.
"""

import requests
from django.db.models import Avg, Count, Q
from django.db.models.functions import TruncDate
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.jobs.models import Job
from apps.scheduling.models import ScheduledEmail
from .models import Output


class ModelStatsView(APIView):
    """
    GET /api/v1/stats/models/
    Returns avg quality score, avg latency, avg tokens/sec, avg user rating,
    and total generations, grouped by model and format.
    Query is exact per PRD 14.2.
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        stats_data = (
            Output.objects.filter(job__user=request.user)
            .values("job__model", "format")
            .annotate(
                avg_latency_ms=Avg("latency_ms"),
                avg_quality_score=Avg("quality_score"),
                avg_tokens_per_second=Avg("tokens_per_second"),
                avg_user_rating=Avg("user_rating"),
                total_generations=Count("id"),
            )
            .order_by("job__model", "format")
        )
        # Return the result in list comprehension with a dictionary inside it for all the items.
        results = [
            {
                "model": row["job__model"],
                "format": row["format"],
                "avg_quality_score": round(row["avg_quality_score"] or 0, 1),
                "avg_latency_ms": round(row["avg_latency_ms"] or 0, 1),
                "avg_tokens_per_second": round(row["avg_tokens_per_second"] or 0, 1),
                "avg_user_rating": (
                    round(row["avg_user_rating"], 1)
                    if row["avg_user_rating"] is not None
                    else None
                ),
                "total_generations": row["total_generations"],
            }
            for row in stats_data
        ]
        return Response(results)


class SummaryStatsView(APIView):
    """
    GET /api/v1/stats/summary/
    Returns { total_jobs, total_outputs, best_model_overall, avg_quality_score }
    for the user's profile card.
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        total_jobs = Job.objects.filter(user=request.user).count()
        total_outputs = Output.objects.filter(job__user=request.user).count()

        overall_avg = Output.objects.filter(job__user=request.user).aggregate(
            avg_quality_score=Avg("quality_score")
        )["avg_quality_score"]

        best_model_row = (
            Output.objects.filter(job__user=request.user)
            .values("job__model")
            .annotate(avg_quality_score=Avg("quality_score"))
            .order_by("-avg_quality_score")
            .first()
        )

        best_model_overall = best_model_row["job__model"] if best_model_row else None

        return Response(
            {
                "total_jobs": total_jobs,
                "total_outputs": total_outputs,
                "best_model_overall": best_model_overall,
                "avg_quality_score": (
                    round(overall_avg, 1) if overall_avg is not None else 0
                ),
            }
        )


class SchedulingStatsView(APIView):
    """
    GET /api/v1/stats/scheduling/
    Returns scheduled-email status counts and daily activity for the
    current user only — this app has no cross-user analytics surface.
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        qs = ScheduledEmail.objects.filter(user=request.user)

        status_counts = {
            row["status"]: row["count"]
            for row in qs.values("status").annotate(count=Count("id"))
        }

        activity = (
            qs.annotate(day=TruncDate("created_at"))
            .values("day")
            .annotate(
                scheduled_count=Count("id"),
                sent_count=Count("id", filter=Q(status="sent")),
            )
            .order_by("day")
        )

        return Response(
            {
                "status_counts": {
                    key: status_counts.get(key, 0)
                    for key, _ in ScheduledEmail.STATUS_CHOICES
                },
                "activity": [
                    {
                        "day": row["day"].isoformat(),
                        "scheduled_count": row["scheduled_count"],
                        "sent_count": row["sent_count"],
                    }
                    for row in activity
                ],
            }
        )
