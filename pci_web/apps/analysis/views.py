import os
import io
import itertools
import logging
from pathlib import Path
from collections import Counter
from datetime import datetime

import pandas as pd
from django.utils.translation import gettext as _, ngettext
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, HttpResponse, JsonResponse
from django.conf import settings
from django.urls import reverse

from apps.projects.models import Project
from apps.sessions.pdf_fonts import BOLD_FONT, REGULAR_FONT, unicode_stylesheet
from apps.sessions.templatetags.condition_labels import pavement_condition_label
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
        detail["img_name"] = stem
        fullist.append((img_file, detail))
        details.append(detail)

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

    # Use same matching logic as results_view
    result_dir = project.results_dir
    result_images = []
    if os.path.isdir(result_dir):
        result_images = sorted(
            f for f in os.listdir(result_dir)
            if f.lower().endswith((".jpg", ".jpeg", ".png"))
        )

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

    empty_detail = {
        "image_name": "", "img_name": "", "pci_rating": 0,
        "crack_len": 0, "alr_area": 0, "patching_area": 0,
        "pothole_area": 0, "pav_condition": "Not Damaged",
    }

    details = []
    for img_file in result_images:
        stem = os.path.splitext(img_file)[0]
        detail = details_by_stem.get(stem, empty_detail.copy())
        detail["img_name"] = img_file  # keep extension for image loading
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
        return HttpResponse(_("Results not available yet."), status=404)

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
    """Redirect to projects page — analysis is accessed per-project."""
    return redirect("projects:index")


@login_required
def export_pdf(request, project_id):
    """Generate a PDF report for PCI analysis results."""
    project = get_object_or_404(Project, user=request.user, pk=project_id)

    _load_results_from_csv(project)
    results = list(project.pci_results.all())

    if not results:
        return HttpResponse(_("No results available for PDF export."), status=404)

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm, cm
        from reportlab.lib.colors import HexColor, black, white
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
            PageBreak, Image as RLImage
        )
        from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
        from reportlab.graphics.shapes import Drawing, Rect, String, Circle
        from reportlab.graphics.charts.piecharts import Pie
        from reportlab.graphics import renderPDF
    except ImportError:
        return HttpResponse(
            _("reportlab is not installed. Run: pip install reportlab"),
            status=500,
        )

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=20*mm, rightMargin=20*mm,
        topMargin=25*mm, bottomMargin=20*mm,
    )
    width, height = A4
    story = []
    styles = unicode_stylesheet()

    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle', parent=styles['Title'],
        fontSize=22, leading=28, spaceAfter=6, textColor=HexColor('#0f172a'),
    )
    subtitle_style = ParagraphStyle(
        'Subtitle', parent=styles['Normal'],
        fontSize=10, textColor=HexColor('#64748b'), spaceAfter=20,
    )
    heading_style = ParagraphStyle(
        'CustomH2', parent=styles['Heading2'],
        fontSize=14, spaceAfter=8, spaceBefore=16,
        textColor=HexColor('#0f172a'),
    )
    body_style = ParagraphStyle(
        'CustomBody', parent=styles['Normal'],
        fontSize=9, leading=13, textColor=HexColor('#334155'),
    )
    small_style = ParagraphStyle(
        'Small', parent=styles['Normal'],
        fontSize=7.5, leading=10, textColor=HexColor('#64748b'),
    )
    table_header_style = ParagraphStyle(
        'TableHeader', parent=styles['Normal'],
        fontName=BOLD_FONT, fontSize=6.5, leading=8,
    )

    def header_cells(labels, color='#0f172a'):
        style = ParagraphStyle('TableHeaderColored', parent=table_header_style, textColor=HexColor(color))
        return [Paragraph(label, style) for label in labels]

    # ===== PAGE 1: TITLE + SUMMARY =====
    story.append(Spacer(1, 10*mm))
    story.append(Paragraph(_("PCI Assessment Report"), title_style))
    story.append(Paragraph(
        _("Project: %(project)s &nbsp;|&nbsp; Generated: %(generated)s &nbsp;|&nbsp; User: %(user)s") % {
            "project": project.name,
            "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "user": request.user.username,
        },
        subtitle_style,
    ))

    # Summary stats
    total_tiles = len(results)
    avg_pci = sum(r.pci_rating for r in results) / total_tiles if total_tiles else 0
    total_km = total_tiles * 10 / 1000
    damaged = sum(
        1 for r in results
        if r.pavement_condition not in ('Not Damaged', 'Good')
    )
    damage_pct = (damaged / total_tiles * 100) if total_tiles else 0

    # Condition label
    if avg_pci > 85:
        cond_label = "Good"
    elif avg_pci > 70:
        cond_label = "Satisfactory"
    elif avg_pci > 55:
        cond_label = "Fair"
    elif avg_pci > 40:
        cond_label = "Poor"
    elif avg_pci > 25:
        cond_label = "Very Poor"
    else:
        cond_label = "Serious / Failed"

    story.append(Paragraph(_("Executive Summary"), heading_style))

    summary_data = [
        [_("Total Length"), _("%(km)s km (%(tiles)s tiles × 10m)") % {"km": f"{total_km:.2f}", "tiles": total_tiles}],
        [_("Average PCI"), f"{avg_pci:.1f}% — {pavement_condition_label(cond_label)}"],
        [_("Damaged Sections"), _("%(count)s of %(total)s (%(percent)s%%)") % {
            "count": damaged, "total": total_tiles, "percent": f"{damage_pct:.1f}",
        }],
        [_("Undamaged Sections"), _("%(count)s of %(total)s") % {"count": total_tiles - damaged, "total": total_tiles}],
    ]
    summary_table = Table(summary_data, colWidths=[55*mm, 100*mm])
    summary_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), BOLD_FONT),
        ('FONTNAME', (1, 0), (1, -1), REGULAR_FONT),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TEXTCOLOR', (0, 0), (0, -1), HexColor('#334155')),
        ('TEXTCOLOR', (1, 0), (1, -1), HexColor('#0f172a')),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('LINEBELOW', (0, 0), (-1, -1), 0.5, HexColor('#e2e8f0')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 8*mm))

    # Condition distribution table
    story.append(Paragraph(_("Condition Distribution"), heading_style))

    cond_counts = Counter(r.pavement_condition for r in results)
    cond_order = [
        'Good', 'Satisfactory', 'Not Damaged', 'Fair',
        'Poor', 'Very Poor', 'Serious', 'Failed',
    ]
    cond_colors = {
        'Good': '#22c55e', 'Satisfactory': '#84cc16',
        'Not Damaged': '#a3e635', 'Fair': '#eab308',
        'Poor': '#f97316', 'Very Poor': '#ef4444',
        'Serious': '#dc2626', 'Failed': '#991b1b',
    }

    dist_header = [_("Condition"), _("Count"), _("Percentage"), ""]
    dist_rows = [dist_header]
    for c in cond_order:
        cnt = cond_counts.get(c, 0)
        if cnt > 0:
            pct = cnt / total_tiles * 100
            bar = "█" * max(1, int(pct / 2))
            dist_rows.append([str(pavement_condition_label(c)), str(cnt), f"{pct:.1f}%", bar])

    dist_table = Table(dist_rows, colWidths=[42*mm, 28*mm, 22*mm, 63*mm])
    dist_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, 0), BOLD_FONT),
        ('FONTNAME', (0, 1), (-1, -1), REGULAR_FONT),
        ('FONTSIZE', (0, 0), (-1, -1), 8.5),
        ('BACKGROUND', (0, 0), (-1, 0), HexColor('#f1f5f9')),
        ('TEXTCOLOR', (0, 0), (-1, 0), HexColor('#334155')),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('LINEBELOW', (0, 0), (-1, 0), 1, HexColor('#cbd5e1')),
        ('LINEBELOW', (0, 1), (-1, -1), 0.5, HexColor('#e2e8f0')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    # Color the bar column per condition
    for i, c in enumerate(cond_order):
        if cond_counts.get(c, 0) > 0:
            row_idx = [r[0] for r in dist_rows].index(str(pavement_condition_label(c)))
            dist_table.setStyle(TableStyle([
                ('TEXTCOLOR', (3, row_idx), (3, row_idx), HexColor(cond_colors[c])),
            ]))
    story.append(dist_table)
    story.append(Spacer(1, 8*mm))

    # Defect type summary
    story.append(Paragraph(_("Defect Type Summary"), heading_style))
    crack_count = sum(1 for r in results if r.crack_length > 0)
    alr_count = sum(1 for r in results if r.alligator_area > 0)
    patch_count = sum(1 for r in results if r.patching_area > 0)
    pot_count = sum(1 for r in results if r.pothole_area > 0)

    defect_data = [
        [_("Defect Type"), _("Sections Affected"), _("Percentage")],
        [_("Longitudinal/Transverse Cracks"), str(crack_count), f"{crack_count/total_tiles*100:.1f}%"],
        [_("Alligator Cracking"), str(alr_count), f"{alr_count/total_tiles*100:.1f}%"],
        [_("Patching"), str(patch_count), f"{patch_count/total_tiles*100:.1f}%"],
        [_("Potholes"), str(pot_count), f"{pot_count/total_tiles*100:.1f}%"],
    ]
    defect_table = Table(defect_data, colWidths=[60*mm, 40*mm, 30*mm])
    defect_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, 0), BOLD_FONT),
        ('FONTNAME', (0, 1), (-1, -1), REGULAR_FONT),
        ('FONTSIZE', (0, 0), (-1, -1), 8.5),
        ('BACKGROUND', (0, 0), (-1, 0), HexColor('#f1f5f9')),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('LINEBELOW', (0, 0), (-1, 0), 1, HexColor('#cbd5e1')),
        ('LINEBELOW', (0, 1), (-1, -1), 0.5, HexColor('#e2e8f0')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(defect_table)

    # ===== PAGE 2: WORST SECTIONS + FULL TABLE =====
    story.append(PageBreak())
    story.append(Paragraph(_("Critical Sections (Worst PCI Scores)"), heading_style))
    story.append(Paragraph(
        _("The following sections have the lowest PCI scores and require priority attention."),
        body_style,
    ))
    story.append(Spacer(1, 4*mm))

    worst = sorted(results, key=lambda r: r.pci_rating)[:15]
    worst_header = header_cells(["#", _("Section"), _("PCI (%)"), _("Condition"), _("Crack (m)"), _("Alligator"), _("Patching"), _("Pothole")], "#991b1b")
    worst_rows = [worst_header]
    for i, r in enumerate(worst, 1):
        worst_rows.append([
            str(i),
            r.image_name[:30] + "..." if len(r.image_name) > 30 else r.image_name,
            f"{r.pci_rating:.1f}",
            str(pavement_condition_label(r.pavement_condition)),
            f"{r.crack_length:.2f}" if r.crack_length > 0 else "—",
            f"{r.alligator_area:.2f}" if r.alligator_area > 0 else "—",
            f"{r.patching_area:.2f}" if r.patching_area > 0 else "—",
            f"{r.pothole_area:.2f}" if r.pothole_area > 0 else "—",
        ])

    worst_table = Table(worst_rows, colWidths=[8*mm, 36*mm, 14*mm, 32*mm, 19*mm, 19*mm, 19*mm, 18*mm])
    worst_style = [
        ('FONTNAME', (0, 0), (-1, 0), BOLD_FONT),
        ('FONTNAME', (0, 1), (-1, -1), REGULAR_FONT),
        ('FONTSIZE', (0, 0), (-1, -1), 7),
        ('BACKGROUND', (0, 0), (-1, 0), HexColor('#fef2f2')),
        ('TEXTCOLOR', (0, 0), (-1, 0), HexColor('#991b1b')),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('LINEBELOW', (0, 0), (-1, 0), 1, HexColor('#fecaca')),
        ('LINEBELOW', (0, 1), (-1, -1), 0.5, HexColor('#e2e8f0')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (2, 0), (2, -1), 'CENTER'),
    ]
    # Highlight severe rows
    for i, r in enumerate(worst, 1):
        if r.pci_rating < 25:
            worst_style.append(('BACKGROUND', (0, i), (-1, i), HexColor('#fef2f2')))
    worst_table.setStyle(TableStyle(worst_style))
    story.append(worst_table)

    # ===== PAGE 3+: FULL RESULTS TABLE =====
    story.append(PageBreak())
    story.append(Paragraph(_("Complete Section Results"), heading_style))
    story.append(Paragraph(
        ngettext(
            "All %(count)d section listed by sequence order.",
            "All %(count)d sections listed by sequence order.",
            total_tiles,
        ) % {"count": total_tiles},
        small_style,
    ))
    story.append(Spacer(1, 3*mm))

    full_header = header_cells(["#", _("Section Name"), "PCI", _("Condition"), _("Crack"), _("Alligator"), _("Patching"), _("Pothole")])
    full_rows = [full_header]
    for i, r in enumerate(results, 1):
        full_rows.append([
            str(i),
            r.image_name[:35] + "..." if len(r.image_name) > 35 else r.image_name,
            f"{r.pci_rating:.1f}",
            str(pavement_condition_label(r.pavement_condition)),
            f"{r.crack_length:.2f}" if r.crack_length > 0 else "—",
            f"{r.alligator_area:.2f}" if r.alligator_area > 0 else "—",
            f"{r.patching_area:.2f}" if r.patching_area > 0 else "—",
            f"{r.pothole_area:.2f}" if r.pothole_area > 0 else "—",
        ])

    full_table = Table(full_rows, colWidths=[8*mm, 40*mm, 12*mm, 32*mm, 18*mm, 19*mm, 19*mm, 17*mm])
    full_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, 0), BOLD_FONT),
        ('FONTNAME', (0, 1), (-1, -1), REGULAR_FONT),
        ('FONTSIZE', (0, 0), (-1, -1), 6.5),
        ('BACKGROUND', (0, 0), (-1, 0), HexColor('#f1f5f9')),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('LINEBELOW', (0, 0), (-1, 0), 1, HexColor('#cbd5e1')),
        ('LINEBELOW', (0, 1), (-1, -1), 0.3, HexColor('#f1f5f9')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (2, 0), (2, -1), 'CENTER'),
    ]))
    story.append(full_table)

    # Footer note
    story.append(Spacer(1, 10*mm))
    story.append(Paragraph(
        _("Report generated by ZaminTwin.ai Road Inspection Platform. PCI evaluation based on ASTM D6433 methodology."),
        small_style,
    ))

    doc.build(story)
    buf.seek(0)

    response = HttpResponse(buf.read(), content_type='application/pdf')
    filename = f"{project.slug}_PCI_Report_{datetime.now().strftime('%Y%m%d')}.pdf"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response
