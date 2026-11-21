from django.db.models import Avg, Count, Q
from django.db.models.functions import TruncDate
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.jobs.models import Job, Output
from apps.scheduling.models import ScheduledEmail


class ModelStatsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        stats_data = (
            Output.objects.for_user(request.user)
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
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        total_jobs = Job.objects.for_user(request.user).count()
        outputs = Output.objects.for_user(request.user)
        total_outputs = outputs.count()

        overall_avg = outputs.aggregate(avg_quality_score=Avg("quality_score"))[
            "avg_quality_score"
        ]

        best_model_row = (
            outputs.values("job__model")
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
                sent_count=Count("id", filter=Q(status=ScheduledEmail.Status.SENT)),
            )
            .order_by("day")
        )

        return Response(
            {
                "status_counts": {
                    key: status_counts.get(key, 0)
                    for key, _ in ScheduledEmail.Status.choices
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
