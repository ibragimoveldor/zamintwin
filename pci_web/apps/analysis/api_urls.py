from django.urls import path
from . import api_views

urlpatterns = [
    path("projects/<int:project_id>/results/", api_views.PCIResultsAPIView.as_view(), name="api-results"),
    path("projects/<int:project_id>/status/", api_views.ProjectStatusAPIView.as_view(), name="api-status"),
]
