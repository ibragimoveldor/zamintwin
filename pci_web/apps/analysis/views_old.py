import os
import itertools
import logging
from pathlib import Path
from collections import Counter

import pandas as pd
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, HttpResponse, JsonResponse
from django.conf import settings
from django.urls import reverse

from apps.projects.models import Project
from .models import PCIResult

logger = logging.getLogger(__name__)


def _load_results_from_csv(project):
    """
    Load PCI results from CSV into the database.
    Called ONCE after pipeline completes, not on every page view.
    """
    csv_path = os.path.join(project.pci_dir, "pci100_final.csv")
    if not os.path.exists(csv_path):
        return False

    # Skip if already loaded
    if project.pci_results.exists():
        return True

    try:
        df = pd.read_csv(csv_path)
        results = []
        for _, row in df.iterrows():
            results.append(
                PCIResult(
                    project=project,
                    image_name=str(row.get("image", "")),
                    pci_rating=float(row.get("PCI", 0)),
                    crack_length=float(row.get("length", 0)),
                    alligator_area=float(row.get("areaAlr", 0)),
                    patching_area=float(row.get("areaPatch", 0)),
                    pothole_area=float(row.get("areaPothole", 0)),
                    pavement_condition=str(
                        row.get("Pavement Condition", "Not Damaged")
                    ),
                )
            )
        PCIResult.objects.bulk_create(results, ignore_conflicts=True)
        return True
    except Exception as e:
        logger.error(f"Failed to load CSV for project {project.pk}: {e}")
        return False


def _get_chart_data(results):
    """
    Generate chart data matching old Google Charts format.
    pie_data: [['Good', 5], ['Fair', 3], ...] for ColumnChart
    bar_data: [['Long&Trans', count, 'red'], ...] for PieChart
    """
    # Pie data: pavement condition distribution
    condition_counts = Counter(r.pavement_condition for r in results)
    pie_data = [[k, v] for k, v in condition_counts.items()]

    # Bar data: crack type occurrences (unique non-zero counts)
    crack_count = sum(1 for r in results if r.crack_length > 0)
    alligator_count = sum(1 for r in results if r.alligator_area > 0)
    patching_count = sum(1 for r in results if r.patching_area > 0)
    pothole_count = sum(1 for r in results if r.pothole_area > 0)

    colors = ["red", "blue", "yellow", "green"]
    labels = ["Long&Trans", "Alligator", "Patching", "Pothole"]
    counts = [crack_count, alligator_count, patching_count, pothole_count]
    bar_data = [
        [label, count, color]
        for label, count, color in zip(labels, counts, colors)
    ]

    return pie_data, bar_data


@login_required
def results_view(request, project_id):
    """Display PCI analysis results for a project."""
    project = get_object_or_404(Project, user=request.user, pk=project_id)

    _load_results_from_csv(project)

    results = list(project.pci_results.all())
    pie_data, bar_data = _get_chart_data(results)

    # Get result images sorted
    result_dir = project.results_dir
    result_images = []
    if os.path.isdir(result_dir):
        result_images = sorted(
            f
            for f in os.listdir(result_dir)
            if f.lower().endswith((".jpg", ".jpeg", ".png"))
        )

    # Build a lookup from image stem to detail dict
    details_by_stem = {}
    for r in results:
        details_by_stem[r.image_name] = {
            "image_name": r.image_name,
            "img_name": r.image_name,
            "pci_rating": r.pci_rating,
            "crack_len": r.crack_length,
            "alr_area": r.alligator_area,
            "patching_area": r.patching_area,
            "pothole_area": r.pothole_area,
            "pav_condition": r.pavement_condition,
        }

    # Build matched list: (image_filename, detail_dict)
    # Match by stem (filename without extension)
    empty_detail = {
        "image_name": "",
        "img_name": "",
        "pci_rating": 0,
        "crack_len": 0,
        "alr_area": 0,
        "patching_area": 0,
        "pothole_area": 0,
        "pav_condition": "Not Damaged",
    }

    fullist = []
    details = []
    for img_file in result_images:
        stem = os.path.splitext(img_file)[0]
        detail = details_by_stem.get(stem, empty_detail.copy())
        detail["img_name"] = stem  # ensure img_name has the stem for GPS parsing
        fullist.append((img_file, detail))
        details.append(detail)

    # Also add any DB results that don't have a matching result image
    # matched_stems = {os.path.splitext(f)[0] for f in result_images}
    # for r_name, detail in details_by_stem.items():
    #     if r_name not in matched_stems:
    #         fullist.append((r_name + ".jpg", detail))
    #         details.append(detail)

    # fullist2: (detail, image_filename) for maintenance section
    fullist2 = [(d, img) for img, d in fullist]

    # Paths for template
    result_path = f"{project.slug}/result/"
    images_path = f"{project.slug}/images/"

    context = {
        "project": project,
        "details": details,
        "images": [img for img, _ in fullist],
        "image_path": result_path,
        "image_raw": images_path,
        "fullist": fullist,
        "fullist2": fullist2,
        "pie_data": pie_data,
        "bar_data": bar_data,
    }
    return render(request, "analyze/analysis.html", context)


@login_required
def map_view(request, project_id):
    """Display PCI results on a map."""
    project = get_object_or_404(Project, user=request.user, pk=project_id)

    _load_results_from_csv(project)
    results = list(project.pci_results.all())

    # Get result images with extensions
    result_dir = project.results_dir
    img_extensions = {}
    if os.path.isdir(result_dir):
        for f in os.listdir(result_dir):
            stem = Path(f).stem
            ext = Path(f).suffix
            img_extensions[stem] = ext

    details = []
    for r in results:
        detail = {
            "image_name": r.image_name,
            "img_name": r.image_name + img_extensions.get(r.image_name, ""),
            "pci_rating": r.pci_rating,
            "crack_len": r.crack_length,
            "alr_area": r.alligator_area,
            "patching_area": r.patching_area,
            "pothole_area": r.pothole_area,
            "pav_condition": r.pavement_condition,
        }
        details.append(detail)

    context = {
        "project": project,
        "details": details,
        "image_path": f"{project.slug}/result/",
        "image_raw": f"{project.slug}/images/",
    }
    return render(request, "analyze/mapview.html", context)


@login_required
def download_csv(request, project_id):
    """Download PCI results as CSV."""
    project = get_object_or_404(Project, user=request.user, pk=project_id)
    csv_path = os.path.join(project.pci_dir, "pci100_final.csv")

    if not os.path.exists(csv_path):
        return HttpResponse("Results not available yet.", status=404)

    response = FileResponse(
        open(csv_path, "rb"),
        content_type="text/csv",
    )
    response["Content-Disposition"] = (
        f'attachment; filename="{project.slug}_pci_results.csv"'
    )
    return response


@login_required
def index_view(request):
    """List projects available for analysis (same as old analyze_index)."""
    projects = Project.objects.filter(user=request.user).order_by("-created_at")
    return render(request, "photogram/index.html", {"projects": projects})
