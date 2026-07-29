"""
Unified API URL configuration.

All API endpoints under /api/v1/.
"""

from django.urls import path

from apps.analysis.api_views import PCIResultsAPIView, ProjectStatusAPIView

urlpatterns = [
    # Analysis
    path("projects/<int:project_id>/results/", PCIResultsAPIView.as_view(), name="api-results"),
    path("projects/<int:project_id>/status/", ProjectStatusAPIView.as_view(), name="api-status"),
]
