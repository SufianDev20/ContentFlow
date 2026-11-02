"""
Scheduled email views.

Endpoints:
    POST   /api/v1/scheduled-emails/                — schedule an email-format output
    GET    /api/v1/scheduled-emails/                — list current user's scheduled emails
    PATCH  /api/v1/scheduled-emails/<uuid:pk>/       — edit content/recipients/time
    POST   /api/v1/scheduled-emails/<uuid:pk>/cancel/ — cancel before it sends

Design decisions:
    - get_queryset() filters by request.user directly (ScheduledEmail.user
      is denormalized), not through output__job__user — matches the hard
      no-cross-user-access rule while staying a single-field filter.
    - Cancel is a dedicated action (not a PATCH to status) so it can be
      idempotent-checked and excluded from the general edit serializer.
"""

from rest_framework import generics, permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ScheduledEmail
from .serializers import (
    EDITABLE_STATUSES,
    ScheduledEmailCreateSerializer,
    ScheduledEmailSerializer,
    ScheduledEmailUpdateSerializer,
)
from .throttles import ScheduledEmailCreateThrottle


class ScheduledEmailListCreateView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [ScheduledEmailCreateThrottle]

    def get_queryset(self):
        qs = ScheduledEmail.objects.filter(user=self.request.user).select_related(
            "output"
        )
        status_filter = self.request.query_params.get("status")
        output_id = self.request.query_params.get("output_id")
        if status_filter:
            qs = qs.filter(status=status_filter)
        if output_id:
            qs = qs.filter(output_id=output_id)
        return qs

    def get_serializer_class(self):
        if self.request.method == "POST":
            return ScheduledEmailCreateSerializer
        return ScheduledEmailSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        read_serializer = ScheduledEmailSerializer(serializer.instance)
        return Response(read_serializer.data, status=status.HTTP_201_CREATED)


class ScheduledEmailUpdateView(generics.UpdateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ScheduledEmailUpdateSerializer
    http_method_names = ["patch"]

    def get_queryset(self):
        return ScheduledEmail.objects.filter(user=self.request.user)

    def update(self, request, *args, **kwargs):
        super().update(request, *args, **kwargs)
        read_serializer = ScheduledEmailSerializer(self.get_object())
        return Response(read_serializer.data)


class ScheduledEmailCancelView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            scheduled_email = ScheduledEmail.objects.get(pk=pk, user=request.user)
        except ScheduledEmail.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        if scheduled_email.status not in EDITABLE_STATUSES:
            raise ValidationError(
                {"detail": f"Cannot cancel a {scheduled_email.status} scheduled email."}
            )

        scheduled_email.status = "cancelled"
        scheduled_email.save(update_fields=["status", "updated_at"])
        return Response(ScheduledEmailSerializer(scheduled_email).data)
