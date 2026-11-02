from django.urls import path
from . import views

urlpatterns = [
    path("stats/models/", views.ModelStatsView.as_view(), name="stats-models"),
    path("stats/summary/", views.SummaryStatsView.as_view(), name="stats-summary"),
    path(
        "stats/scheduling/",
        views.SchedulingStatsView.as_view(),
        name="stats-scheduling",
    ),
]
