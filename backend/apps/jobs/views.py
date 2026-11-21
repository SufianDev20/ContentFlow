import logging

import requests
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
)
from rest_framework import generics, permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from .models import Job, Output
from .serializers import (
    JobCreateSerializer,
    JobDetailSerializer,
    JobListSerializer,
    OutputRateSerializer,
    OutputSerializer,
    ScrapeRequestSerializer,
    ScrapeResponseSerializer,
)
from .services import llm
from .services.repurposer import repurpose
from .services.scraper import fetch_from_url
from .throttles import (
    JobCreateBurstThrottle,
    JobCreateDailyThrottle,
    ScrapeThrottle,
)

logger = logging.getLogger(__name__)


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
    throttle_classes = [UserRateThrottle, JobCreateBurstThrottle, JobCreateDailyThrottle]
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Job.objects.for_user(self.request.user).order_by("-created_at")

    def get_serializer_class(self):
        if self.request.method == "POST":
            return JobCreateSerializer
        return JobListSerializer

    def create(self, request, *args, **kwargs):
        # Generation runs synchronously here; a task queue would return 202 instead.
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        job = serializer.save(user=request.user)
        repurpose(job)
        return Response(
            JobDetailSerializer(job, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


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
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = JobDetailSerializer

    def get_queryset(self):
        return Job.objects.for_user(self.request.user).prefetch_related("outputs")


@extend_schema(
    tags=["outputs"],
    summary="List generated content outputs",
    description="Returns paginated list of outputs with optional filtering by format and model.",
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
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = OutputSerializer

    def get_queryset(self):
        qs = Output.objects.for_user(self.request.user).select_related("job")
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
    description="Submit a star rating (1-5) for a specific output.",
    responses={
        200: OutputRateSerializer,
        400: OpenApiResponse(description="Invalid rating value"),
        401: OpenApiResponse(description="Authentication required"),
        404: OpenApiResponse(description="Output not found"),
    },
)
class OutputRateView(generics.UpdateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = OutputRateSerializer
    http_method_names = ["patch"]

    def get_queryset(self):
        return Output.objects.for_user(self.request.user)


@extend_schema(
    tags=["jobs"],
    summary="Fetch article content from URL",
    description="Scrapes article text from a provided URL. Returns title, text content, and word count. No database writes.",
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
        except requests.exceptions.RequestException:
            logger.exception("Scrape failed for URL %s", url)
            return Response(
                {"detail": "Failed to fetch the URL."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response(ScrapeResponseSerializer(result).data)


@extend_schema(
    tags=["jobs"],
    summary="Get available AI models",
    description="Free model ids per provider: OpenRouter (fetched live) and Gemini.",
    responses={
        200: OpenApiTypes.OBJECT,
        401: OpenApiResponse(description="Authentication required"),
    },
)
class AvailableModelsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(llm.available_models())
