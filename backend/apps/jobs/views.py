"""
Job and Output views for ContentFlow AI.

Endpoints:
    POST   /api/v1/jobs/                  — create and process a job
    GET    /api/v1/jobs/                  — list current user's jobs (paginated)
    GET    /api/v1/jobs/<uuid:pk>/        — retrieve one job with outputs
    DELETE /api/v1/jobs/<uuid:pk>/        — delete a job and its outputs
    GET    /api/v1/outputs/               — list outputs; filter by format or model
    PATCH  /api/v1/outputs/<uuid:pk>/rate/ — submit a star rating
    POST   /api/v1/scrape/               — fetch article text from a URL

Design decisions:
    - get_queryset() filters by request.user on every view — no output
      from another user is ever reachable, regardless of UUID guessing.
    - JobListCreateView.perform_create() runs the full service pipeline
      synchronously (v1.0). When Celery is added, replace the service
      call here with a task dispatch and return 202 Accepted.
    - OutputRateView uses PATCH (partial update) — only user_rating changes.
    - ScrapeView is stateless; it does not create any DB record.
    - Service exceptions surface as 400/502 rather than 500 by catching
      at the view boundary.
"""

import logging
from django.shortcuts import render
from rest_framework import generics, permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, OpenApiExample, OpenApiResponse, OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from .models import Job
from apps.stats.models import Output
from .serializers import (
    JobCreateSerializer,
    JobDetailSerializer,
    JobListSerializer,
    OutputRateSerializer,
    OutputSerializer,
    ScrapeRequestSerializer,
    ScrapeResponseSerializer,
)
from .services.repurposer import repurpose, get_available_free_model
from .services.scraper import fetch_from_url
from .throttles import (
    JobCreateBurstThrottle,
    JobCreateDailyThrottle,
    ScrapeThrottle,
)

logger = logging.getLogger(__name__)


# Create your views here.
@extend_schema(
    tags=["jobs"],
    summary="List and create content generation jobs",
    description="GET returns paginated list of user's jobs. POST creates a new job and runs content generation.",
    responses={
        200: JobListSerializer,
        201: JobDetailSerializer,
        400: OpenApiResponse(description="Invalid input data"),
        401: OpenApiResponse(description="Authentication required"),
        429: OpenApiResponse(description="Rate limit exceeded"),
    },
)
class JobListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/v1/jobs/  — paginated job list for the current user.
    POST /api/v1/jobs/  — create a job, run repurposing, return full outputs.

    Pagination is handled by DEFAULT_PAGINATION_CLASS in settings.py
    (PageNumberPagination, page_size=20). No extra code needed here.
    """

    throttle_classes = [JobCreateBurstThrottle, JobCreateDailyThrottle]
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return (
            Job.objects.filter(user=self.request.user)
            .prefetch_related("outputs")
            .order_by("-created_at")
        )

    def get_serializer_class(self):
        """
        Serializer class to be called based on POST when we create a job and else the list of jobs built for it.
        """
        if self.request.method == "POST":
            return JobCreateSerializer
        return JobListSerializer

    def perform_create(self, serializer):
        """
        Save the Job record, run the repurposing pipeline, then flip
        status to complete or failed.

        When Celery is introduced:
          1. Remove the repurpose() call here.
          2. Dispatch a Celery task with job.id.
          3. Return 202 Accepted from create().
        """
        job = serializer.save(user=self.request.user)
        try:
            results = repurpose(job)
            job.status = "complete" if results else "failed"
        except Exception as exc:
            logger.exception(f"Repurposing failed for job {job.id}")
            job.status = "failed"
            job.save(update_fields=["status"])
            raise ValidationError({"detail": "Generation Failed. Try Again"}) from exc
        job.save(update_fields=["status"])

    def create(self, request, *args, **kwargs):
        """Return full job detail (with outputs) after creation, not just the input fields."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        job = serializer.instance
        job.refresh_from_db()
        output_serializer = JobDetailSerializer(job, context={"request": request})
        return Response(output_serializer.data, status=status.HTTP_201_CREATED)


@extend_schema(
    tags=["jobs"],
    summary="Retrieve or delete a specific job",
    description="GET returns full job details with all outputs. DELETE removes the job and all associated outputs.",
    responses={
        200: JobDetailSerializer,
        204: OpenApiResponse(description="Job deleted successfully"),
        401: OpenApiResponse(description="Authentication required"),
        404: OpenApiResponse(description="Job not found"),
    },
)
class JobDetailView(generics.RetrieveDestroyAPIView):
    """
    GET    /api/v1/jobs/<uuid:pk>/  — full job with all outputs and metrics.
    DELETE /api/v1/jobs/<uuid:pk>/  — cascade-deletes all linked outputs.
    """

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = JobDetailSerializer

    def get_queryset(self):
        return Job.objects.filter(user=self.request.user).prefetch_related("outputs")


@extend_schema(
    tags=["outputs"],
    summary="List generated content outputs",
    description="Returns paginated list of outputs with optional filtering by format and model. Supports query parameters: ?format=tweet_thread&model=openai/gpt-4o",
    parameters=[
        OpenApiParameter(
            name="format",
            type=OpenApiTypes.STR,
            description="Filter by output format (tweet_thread, linkedin, email, tldr)",
            required=False,
        ),
        OpenApiParameter(
            name="model",
            type=OpenApiTypes.STR,
            description="Filter by AI model used",
            required=False,
        ),
    ],
    responses={
        200: OutputSerializer,
        401: OpenApiResponse(description="Authentication required"),
    },
)
class OutputListView(generics.ListAPIView):
    """
    GET /api/v1/outputs/

    Supports ?format=tweet_thread and ?model=openai/gpt-4o query params.
    Filters are additive (both params applied together if both present).
    """

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = OutputSerializer

    def get_queryset(self):
        qs = Output.objects.filter(job__user=self.request.user).select_related("job")
        fmt = self.request.query_params.get("format")
        model = self.request.query_params.get("model")
        if fmt:
            qs = qs.filter(format=fmt)
        if model:
            qs = qs.filter(job__model=model)
        return qs.order_by("-created_at")


@extend_schema(
    tags=["outputs"],
    summary="Rate a generated output",
    description="Submit a star rating (1-5) for a specific output. Uses PATCH method for partial update.",
    responses={
        200: OutputRateSerializer,
        400: OpenApiResponse(description="Invalid rating value"),
        401: OpenApiResponse(description="Authentication required"),
        404: OpenApiResponse(description="Output not found"),
    },
)
class OutputRateView(generics.UpdateAPIView):
    """
    PATCH /api/v1/outputs/<uuid:pk>/rate/

    Only updates user_rating. PATCH is correct here — no other field changes.
    HTTP 405 is returned for PUT automatically by DRF since http_method_names
    excludes it via the router.
    """

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = OutputRateSerializer
    http_method_names = ["patch"]

    def get_queryset(self):
        # Scopes to the current user's outputs via the job FK chain.
        return Output.objects.filter(job__user=self.request.user)


@extend_schema(
    tags=["jobs"],
    summary="Fetch article content from URL",
    description="Scrapes article text from a provided URL. Returns title, text content, and word count. Stateless operation - no database writes.",
    request=ScrapeRequestSerializer,
    responses={
        200: ScrapeResponseSerializer,
        400: OpenApiResponse(description="Invalid URL or scraping failed"),
        401: OpenApiResponse(description="Authentication required"),
        429: OpenApiResponse(description="Rate limit exceeded"),
        502: OpenApiResponse(description="Upstream fetch failed"),
    },
)
class ScrapeView(APIView):
    """
    POST /api/v1/scrape/

    Stateless — no DB writes. Fetches article text from a URL and
    returns { text, word_count, title }.
    Errors from the scraper surface as 400 (bad URL / no content)
    or 502 (upstream fetch failed).
    """

    throttle_classes = [ScrapeThrottle]
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        request_serializer = ScrapeRequestSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        url = request_serializer.validated_data["url"]

        try:
            result = fetch_from_url(url)
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        except Exception:
            logger.exception("Scrape failed for URL %s", url)
            return Response(
                {"detail": "Failed to fetch the URL."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        response_serializer = ScrapeResponseSerializer(result)
        return Response(response_serializer.data, status=status.HTTP_200_OK)


@extend_schema(
    tags=["jobs"],
    summary="Get available AI models",
    description="Returns list of currently available free AI models from OpenRouter and Gemini. Fetched live from provider APIs.",
    responses={
        200: OpenApiTypes.OBJECT,
        401: OpenApiResponse(description="Authentication required"),
    },
)
class AvailableModelsView(APIView):
    """
    GET /api/v1/models/available/

    Returns the list of currently free model IDs available on OpenRouter.

    No serializer is used here since the response is a plain list of
    model ID strings, not a Django model instance. Model list is fetched
    live from OpenRouter's /models endpoint via get_free_models_list().

    Response body: {"models": ["<model_id>", ...]}
    Falls back to a single hardcoded model if the OpenRouter call fails.
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response({"models": get_available_free_model()})


@extend_schema(
    tags=["jobs"],
    summary="Get job generation status",
    description="Returns real-time job status with progress percentage for frontend polling. Includes completed formats count and total formats.",
    responses={
        200: OpenApiTypes.OBJECT,
        401: OpenApiResponse(description="Authentication required"),
        404: OpenApiResponse(description="Job not found"),
    },
)
class JobStatusView(generics.RetrieveAPIView):
    """
    GET /api/v1/jobs/<uuid:pk>/status/

    Returns job status with progress information for polling.
    Used by frontend to track generation progress.
    """

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = JobDetailSerializer

    def get_queryset(self):
        return Job.objects.filter(user=self.request.user).prefetch_related("outputs")

    def retrieve(self, request, *args, **kwargs):
        job = self.get_object()
        total_formats = len(job.formats) if job.formats else 4
        completed_outputs = job.outputs.count()
        progress_percentage = int((completed_outputs / total_formats) * 100) if total_formats > 0 else 0

        return Response({
            "id": str(job.id),
            "status": job.status,
            "progress": progress_percentage,
            "total_formats": total_formats,
            "completed_outputs": completed_outputs,
            "created_at": job.created_at,
        })
