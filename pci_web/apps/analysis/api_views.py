from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404

from apps.projects.models import Project
from .models import PCIResult


class ProjectStatusAPIView(APIView):
    """Poll project processing status (for async UI updates)."""

    def get(self, request, project_id):
        project = get_object_or_404(Project, user=request.user, pk=project_id)
        return Response(
            {
                "id": project.pk,
                "name": project.name,
                "status": project.status,
                "status_display": project.get_status_display(),
            }
        )


class PCIResultsAPIView(APIView):
    """Get PCI results as JSON."""

    def get(self, request, project_id):
        project = get_object_or_404(Project, user=request.user, pk=project_id)
        results = PCIResult.objects.filter(project=project).values(
            "image_name",
            "pci_rating",
            "crack_length",
            "alligator_area",
            "patching_area",
            "pothole_area",
            "pavement_condition",
        )
        return Response({"project": project.name, "results": list(results)})
