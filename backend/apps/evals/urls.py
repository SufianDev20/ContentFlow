from django.urls import path

from . import views

app_name = "evals"

urlpatterns = [
    path("evals/runs/", views.EvalRunListView.as_view(), name="run-list"),
    path("evals/runs/<uuid:pk>/", views.EvalRunDetailView.as_view(), name="run-detail"),
    path("evals/runs/<uuid:run_pk>/results/", views.EvalResultListView.as_view(), name="result-list"),
    path("evals/articles/", views.EvalArticleListView.as_view(), name="article-list"),
]
