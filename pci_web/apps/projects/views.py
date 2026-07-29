import os
import shutil
import logging

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from django.conf import settings

from .models import Project, ProjectImage
from .forms import ProjectCreateForm, ImageUploadForm
from .tasks import run_pci_pipeline

logger = logging.getLogger(__name__)


def index(request):
    """Redirect to login for anonymous users, project list for authenticated."""
    if not request.user.is_authenticated:
        return redirect('/accounts/login/')

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
            try:
                img = ProjectImage(project=project, image=file)
                img.full_clean()
                img.save()
                success_count += 1
            except Exception as e:
                logger.warning(f"Failed to save image {file.name}: {e}")

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


@login_required
def project_status(request, project_id):
    """AJAX endpoint for polling project processing status."""
    from django.http import JsonResponse
    from collections import Counter
    project = get_object_or_404(Project, user=request.user, pk=project_id)

    data = {
        "status": project.status,
        "status_label": project.get_status_display(),
        "image_count": project.images.count(),
    }

    # Include PCI stats for completed projects
    if project.status == Project.Status.COMPLETED:
        try:
            from apps.analysis.models import PCIResult
            results = list(project.pci_results.all())
            if results:
                total = len(results)
                avg_pci = sum(r.pci_rating for r in results) / total
                cond_counts = Counter(r.pavement_condition for r in results)
                data.update({
                    "tiles": total,
                    "avg_pci": round(avg_pci, 1),
                    "conditions": dict(cond_counts),
                })
        except Exception:
            pass

    return JsonResponse(data)


@login_required
def projects_summary(request):
    """AJAX endpoint returning PCI summary for all completed projects."""
    from django.http import JsonResponse
    from collections import Counter

    projects = Project.objects.filter(user=request.user, status=Project.Status.COMPLETED)
    summaries = {}

    for project in projects:
        try:
            result_dir = project.results_dir
            if not os.path.isdir(result_dir):
                continue

            result_images = sorted(
                f for f in os.listdir(result_dir)
                if f.lower().endswith(('.jpg', '.jpeg', '.png'))
            )
            if not result_images:
                continue

            # Build lookup from DB
            results = list(project.pci_results.all())
            by_stem = {}
            for r in results:
                by_stem[r.image_name] = r

            # Match ALL result images (same as dashboard)
            # Unmatched images get PCI=0 and "Not Damaged"
            total = len(result_images)
            total_pci = 0.0
            cond_counts = Counter()
            for img_file in result_images:
                stem = os.path.splitext(img_file)[0]
                r = by_stem.get(stem)
                if r:
                    total_pci += r.pci_rating
                    cond_counts[r.pavement_condition] += 1
                else:
                    total_pci += 0
                    cond_counts["Not Damaged"] += 1

            avg_pci = total_pci / total if total else 0
            summaries[str(project.id)] = {
                "tiles": total,
                "avg_pci": round(avg_pci, 1),
                "conditions": dict(cond_counts),
            }
        except Exception as e:
            logger.error(f"Error loading stats for project {project.id}: {e}")

    return JsonResponse({"projects": summaries})
