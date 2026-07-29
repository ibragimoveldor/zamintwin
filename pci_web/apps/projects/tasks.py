"""
Celery tasks for project processing.

Calls the AI service over HTTP instead of importing AI code directly.
This keeps the web app free of torch/YOLO/GPU dependencies.
"""

import logging

import httpx
from celery import shared_task
from django.conf import settings

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def run_pci_pipeline(self, project_id: int, images_dir: str):
    """
    Trigger PCI analysis by calling the AI service over HTTP.

    The AI service loads models once at startup and processes requests.
    This task blocks until processing completes (fine — we're in Celery).
    """
    from apps.projects.models import Project

    ai_url = getattr(settings, "AI_SERVICE_URL", "http://localhost:8001")
    timeout = getattr(settings, "AI_SERVICE_TIMEOUT", 600)

    try:
        logger.info(f"Calling AI service for project {project_id}")

        with httpx.Client(timeout=timeout) as client:
            response = client.post(
                f"{ai_url}/api/v1/analyze",
                json={
                    "project_id": project_id,
                    "images_dir": images_dir,
                },
            )

        if response.status_code == 200:
            result = response.json()
            logger.info(f"Pipeline completed: {result['message']}")
            Project.objects.filter(pk=project_id).update(status=Project.Status.COMPLETED)
            return result

        elif response.status_code == 503:
            logger.warning("AI service models still loading, retrying...")
            raise self.retry(countdown=15)

        else:
            error_detail = response.json().get("detail", response.text)
            logger.error(f"AI service error ({response.status_code}): {error_detail}")
            Project.objects.filter(pk=project_id).update(status=Project.Status.FAILED)
            raise Exception(f"AI service returned {response.status_code}: {error_detail}")

    except httpx.ConnectError:
        logger.error("Cannot connect to AI service — is it running?")
        raise self.retry(countdown=30)

    except httpx.TimeoutException:
        logger.error(f"AI service timed out after {timeout}s")
        Project.objects.filter(pk=project_id).update(status=Project.Status.FAILED)
        raise
