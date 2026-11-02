from django.urls import path
from . import views

urlpatterns = [
    path("jobs/", views.JobListCreateView.as_view(), name="job-list-create"),
    path("jobs/<uuid:pk>/", views.JobDetailView.as_view(), name="job-detail"),
    path("jobs/<uuid:pk>/status/", views.JobStatusView.as_view(), name="job-status"),
    path("outputs/", views.OutputListView.as_view(), name="output-list"),
    path("outputs/<uuid:pk>/rate/", views.OutputRateView.as_view(), name="output-rate"),
    path("scrape/", views.ScrapeView.as_view(), name="scrape"),
    path(
        "models/available/",
        views.AvailableModelsView.as_view(),
        name="models-available",
    ),
]
