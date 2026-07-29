import shutil
import logging

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from django.conf import settings

from .models import Project
from .forms import ProjectCreateForm, ImageUploadForm
from .tasks import run_pci_pipeline

logger = logging.getLogger(__name__)


def index(request):
    """Show landing page for anonymous users, project list for logged-in users."""
    if not request.user.is_authenticated:
        return render(request, "landing.html")

    msg = {"type": "", "msg": ""}

    if request.method == "POST":
        form = ProjectCreateForm(request.POST, user=request.user)
        if form.is_valid():
            project = form.save(commit=False)
            project.user = request.user
            project.save()
            msg = {"type": "success", "msg": "Project created successfully!"}
            form = ProjectCreateForm()
        else:
            msg = {"type": "warning", "msg": "Project creation failed. Please try again."}
    else:
        form = ProjectCreateForm()

    context = {
        "folder_form": form,
        "projects": Project.objects.filter(user=request.user),
        "msg": msg,
    }
    return render(request, "photogram/index.html", context)


@login_required
def upload(request, project_id):
    """Upload images to a project."""
    project = get_object_or_404(Project, user=request.user, pk=project_id)
    msg = {"type": "", "msg": ""}

    if request.method == "POST":
        files = request.FILES.getlist("image")
        success_count = 0
        for file in files:
            form = ImageUploadForm(request.POST, {"image": file})
            if form.is_valid():
                img = form.save(commit=False)
                img.project = project
                img.save()
                success_count += 1

        if success_count > 0:
            project.status = Project.Status.UPLOADED
            project.save()
            msg = {"type": "success", "msg": f"{success_count} images uploaded successfully!"}
        else:
            msg = {"type": "warning", "msg": "No images were uploaded."}

    context = {
        "file_form": ImageUploadForm(),
        "project": project,
        "msg": msg,
    }
    return render(request, "photogram/upload.html", context)


@login_required
def process(request, project_id):
    """Trigger PCI analysis pipeline via Celery."""
    if request.method == "POST":
        project = get_object_or_404(Project, user=request.user, pk=project_id)

        # Don't re-process if already running
        if project.status == Project.Status.PROCESSING:
            return redirect(reverse("projects:index"))

        project.status = Project.Status.PROCESSING
        project.save()

        # Dispatch to Celery (which calls the AI service over HTTP)
        task = run_pci_pipeline.delay(
            project_id=project.pk,
            images_dir=project.images_dir,
        )

        project.celery_task_id = task.id
        project.save()

    return redirect(reverse("projects:index"))


@login_required
def delete(request, project_id):
    """Delete a project and its files."""
    if request.method == "POST":
        project = get_object_or_404(Project, user=request.user, pk=project_id)
        # Remove files from disk
        project_dir = project.images_dir.replace("/images", "")
        shutil.rmtree(project_dir, ignore_errors=True)
        project.delete()

    return redirect(reverse("projects:index"))
