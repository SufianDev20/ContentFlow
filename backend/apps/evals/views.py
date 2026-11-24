from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.permissions import IsAdminUser

from .models import EvalArticle, EvalRun, EvalResult
from .serializers import (
    EvalArticleSerializer,
    EvalRunListSerializer,
    EvalRunDetailSerializer,
    EvalResultSerializer,
)


class EvalRunListView(ListAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = EvalRunListSerializer
    queryset = EvalRun.objects.all()


class EvalRunDetailView(RetrieveAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = EvalRunDetailSerializer
    queryset = EvalRun.objects.prefetch_related("results__article")


class EvalResultListView(ListAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = EvalResultSerializer

    def get_queryset(self):
        qs = EvalResult.objects.filter(
            run_id=self.kwargs["run_pk"]
        ).select_related("article")

        fmt = self.request.query_params.get("format")
        if fmt:
            qs = qs.filter(format=fmt)

        passed = self.request.query_params.get("passed")
        if passed is not None:
            qs = qs.filter(passed=passed.lower() == "true")

        return qs


class EvalArticleListView(ListAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = EvalArticleSerializer
    queryset = EvalArticle.objects.all()
