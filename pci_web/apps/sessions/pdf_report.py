"""
PDF Report Generator for Road Inspection Sessions.
Produces a branded, professional PDF with:
  - Page 1: Cover + Executive Summary (PCI score, distance, defect counts)
  - Page 2: PCI along road chart, Top 10 worst segments, PCI history trend
  - Page 3: Defect inventory with type breakdown and severity distribution
  - Page 4: Recommendations
"""
import io
from datetime import datetime

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required
from django.utils.translation import gettext as _, gettext_noop, ngettext

from .models import Session, Detection, RoadSegment
from .pdf_fonts import BOLD_FONT, REGULAR_FONT, unicode_stylesheet
from .templatetags.condition_labels import RATING_LABELS, SEVERITY_LABELS

# Defect display names
DEFECT_NAMES = {
    "D00": gettext_noop("Longitudinal crack"),
    "D10": gettext_noop("Transverse crack"),
    "D20": gettext_noop("Alligator crack"),
    "D40": gettext_noop("Pothole"),
    "D50": gettext_noop("Pothole"),
    "pothole": gettext_noop("Pothole"),
    "alligator_crack": gettext_noop("Alligator crack"),
    "longitudinal_crack": gettext_noop("Longitudinal crack"),
    "transverse_crack": gettext_noop("Transverse crack"),
    "patch": gettext_noop("Patch/repair"),
    "rutting": gettext_noop("Rutting"),
    "bleeding": gettext_noop("Bleeding"),
}


def _defect_name(raw):
    return DEFECT_NAMES.get(raw, raw.replace("_", " ").title())


def _rating_label(rating):
    return str(RATING_LABELS.get(rating, (rating or "—").replace("_", " ").title()))


def _severity_label(severity):
    return str(SEVERITY_LABELS.get(severity, severity.title()))


# PCI condition colors
CONDITION_COLORS = {
    "good": "#22c55e",
    "satisfactory": "#84cc16",
    "fair": "#eab308",
    "poor": "#f97316",
    "very_poor": "#ef4444",
    "failed": "#991b1b",
}

SEVERITY_COLORS = {
    "critical": "#ef4444",
    "high": "#f97316",
    "medium": "#eab308",
    "low": "#84cc16",
}


@login_required
def session_pdf_report(request, session_id):
    """Generate a branded PDF report for a session."""
    session = get_object_or_404(Session, pk=session_id, user=request.user)

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.lib.colors import HexColor, black, white
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
            PageBreak,
        )
        from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
        from reportlab.graphics.shapes import Drawing, Rect, String
        from reportlab.graphics import renderPDF
    except ImportError:
        return HttpResponse(
            _("reportlab is not installed. Run: pip install reportlab"),
            status=500,
        )

    segments = RoadSegment.objects.filter(session=session).order_by("segment_index")
    detections = Detection.objects.filter(
        session=session, is_duplicate=False
    ).order_by("distance_km")

    # ── Prepare data ─────────────────────────────────────────────────
    total_segments = segments.count()
    total_detections = detections.count()
    avg_pci = session.avg_pci or 0
    condition = session.condition_rating or "unknown"
    distance = session.distance_km or 0

    # Defect type counts
    type_counts = {}
    severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for d in detections:
        name = _defect_name(d.defect_type)
        type_counts[name] = type_counts.get(name, 0) + 1
        sev = d.severity
        if sev in severity_counts:
            severity_counts[sev] += 1

    # Condition distribution
    cond_dist = {}
    for seg in segments:
        r = seg.condition_rating or "unknown"
        cond_dist[r] = cond_dist.get(r, 0) + 1

    # ── Build PDF ────────────────────────────────────────────────────
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=25 * mm, bottomMargin=20 * mm,
    )
    width, height = A4
    story = []
    styles = unicode_stylesheet()

    # Custom styles
    brand_color = HexColor("#0f172a")
    accent_color = HexColor("#3b82f6")

    title_style = ParagraphStyle(
        "Title", parent=styles["Title"],
        fontSize=24, leading=30, spaceAfter=4, textColor=brand_color,
        fontName=BOLD_FONT,
    )
    subtitle_style = ParagraphStyle(
        "Subtitle", parent=styles["Normal"],
        fontSize=10, textColor=HexColor("#64748b"), spaceAfter=20,
    )
    h2_style = ParagraphStyle(
        "H2", parent=styles["Heading2"],
        fontSize=14, spaceAfter=8, spaceBefore=16,
        textColor=brand_color, fontName=BOLD_FONT,
    )
    h3_style = ParagraphStyle(
        "H3", parent=styles["Heading3"],
        fontSize=11, spaceAfter=6, spaceBefore=12,
        textColor=HexColor("#334155"), fontName=BOLD_FONT,
    )
    body_style = ParagraphStyle(
        "Body", parent=styles["Normal"],
        fontSize=9, leading=13, textColor=HexColor("#334155"),
    )
    small_style = ParagraphStyle(
        "Small", parent=styles["Normal"],
        fontSize=7.5, leading=10, textColor=HexColor("#94a3b8"),
    )
    center_style = ParagraphStyle(
        "Center", parent=styles["Normal"],
        fontSize=9, alignment=TA_CENTER, textColor=HexColor("#334155"),
    )

    # ═══════════════════════════════════════════════════════════════════
    # PAGE 1: COVER + EXECUTIVE SUMMARY
    # ═══════════════════════════════════════════════════════════════════
    story.append(Spacer(1, 15 * mm))

    # Brand header
    story.append(Paragraph("ZaminTwin.ai", ParagraphStyle(
        "Brand", parent=styles["Normal"],
        fontSize=12, textColor=accent_color, fontName=BOLD_FONT,
        spaceAfter=2,
    )))
    story.append(Paragraph(_("Road Condition Assessment Report"), title_style))
    story.append(Paragraph(
        _("Session: %(session)s &nbsp;|&nbsp; Generated: %(generated)s &nbsp;|&nbsp; Inspector: %(inspector)s") % {
            "session": session.session_id,
            "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "inspector": request.user.get_full_name() or request.user.username,
        },
        subtitle_style,
    ))

    # ── Big PCI Score Box ──
    pci_color = CONDITION_COLORS.get(condition, "#64748b")
    pci_drawing = Drawing(170 * mm, 28 * mm)
    pci_drawing.add(Rect(0, 0, 170 * mm, 28 * mm, rx=4 * mm,
                         fillColor=HexColor(pci_color), fillOpacity=0.1,
                         strokeColor=HexColor(pci_color), strokeWidth=1))
    pci_drawing.add(String(15 * mm, 8 * mm,
                           f"PCI {avg_pci:.1f}  —  {_rating_label(condition)}",
                           fontSize=18, fontName=BOLD_FONT,
                           fillColor=HexColor(pci_color)))
    pci_drawing.add(String(165 * mm, 8 * mm,
                           _("%(distance)s km surveyed") % {"distance": f"{distance:.2f}"},
                           fontSize=10, fontName=REGULAR_FONT,
                           fillColor=HexColor("#64748b"), textAnchor="end"))
    story.append(pci_drawing)
    story.append(Spacer(1, 8 * mm))

    # ── Executive Summary Table ──
    story.append(Paragraph(_("Executive Summary"), h2_style))

    summary_data = [
        [_("Session ID"), session.session_id],
        [_("Date"), session.start_time.strftime("%Y-%m-%d %H:%M") if session.start_time else "—"],
        [_("Distance Surveyed"), f"{distance:.2f} " + _("km")],
        [_("Average PCI Score"), f"{avg_pci:.1f} ({_rating_label(condition)})"],
        [_("Road Segments (100m)"), str(total_segments)],
        [_("Total Defects"), str(total_detections)],
        [_("Defects per km"), f"{(total_detections / distance):.1f}" if distance > 0 else "—"],
        [_("Device"), session.session_metadata.get("device", "Jetson Orin Nano Super") if session.session_metadata else "—"],
        [_("AI Model"), session.session_metadata.get("model", "yolo26s.engine") if session.session_metadata else "—"],
    ]

    t = Table(summary_data, colWidths=[62 * mm, 108 * mm])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), BOLD_FONT),
        ("FONTNAME", (1, 0), (1, -1), REGULAR_FONT),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), HexColor("#64748b")),
        ("TEXTCOLOR", (1, 0), (1, -1), brand_color),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, HexColor("#e2e8f0")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(t)
    story.append(Spacer(1, 8 * mm))

    # ── Condition Distribution ──
    story.append(Paragraph(_("Road Condition Distribution"), h2_style))

    cond_order = ["good", "satisfactory", "fair", "poor", "very_poor", "failed"]
    dist_header = [_("Condition"), _("Segments"), _("Percentage"), ""]
    dist_rows = [dist_header]
    for c in cond_order:
        cnt = cond_dist.get(c, 0)
        if cnt > 0:
            pct = cnt / total_segments * 100 if total_segments else 0
            bar = chr(9608) * max(1, int(pct / 3))
            dist_rows.append([_rating_label(c), str(cnt), f"{pct:.1f}%", bar])

    if len(dist_rows) > 1:
        dt = Table(dist_rows, colWidths=[40 * mm, 25 * mm, 25 * mm, 75 * mm])
        dt.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, 0), BOLD_FONT),
            ("FONTNAME", (0, 1), (-1, -1), REGULAR_FONT),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("BACKGROUND", (0, 0), (-1, 0), HexColor("#f1f5f9")),
            ("TEXTCOLOR", (0, 0), (-1, 0), HexColor("#334155")),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("LINEBELOW", (0, 0), (-1, 0), 1, HexColor("#cbd5e1")),
            ("LINEBELOW", (0, 1), (-1, -1), 0.5, HexColor("#e2e8f0")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        # Color the bar column
        for i, c in enumerate(cond_order):
            if cond_dist.get(c, 0) > 0:
                row_idx = [r[0] for r in dist_rows].index(_rating_label(c))
                clr = CONDITION_COLORS.get(c, "#64748b")
                dt.setStyle(TableStyle([
                    ("TEXTCOLOR", (3, row_idx), (3, row_idx), HexColor(clr)),
                ]))
        story.append(dt)

    # ═══════════════════════════════════════════════════════════════════
    # PAGE 2: PCI ALONG ROAD CHART + WORST SEGMENTS + HISTORY
    # ═══════════════════════════════════════════════════════════════════
    story.append(PageBreak())
    story.append(Paragraph(_("PCI Along Road Profile"), h2_style))
    story.append(Paragraph(
        _("PCI values plotted for each 100-meter segment. Total: %(segments)s segments over %(distance)s km.") % {
            "segments": total_segments,
            "distance": f"{distance:.2f}",
        },
        body_style,
    ))
    story.append(Spacer(1, 4 * mm))

    # ── PCI Along Road Chart (reportlab Drawing/shapes) ──
    from reportlab.graphics.shapes import Line, PolyLine, Group
    chart_w = 160 * mm
    chart_h = 75 * mm
    margin_left = 12 * mm
    margin_bottom = 10 * mm
    margin_top = 4 * mm
    margin_right = 4 * mm
    plot_w = chart_w - margin_left - margin_right
    plot_h = chart_h - margin_bottom - margin_top

    pci_chart = Drawing(chart_w, chart_h)

    # Background condition bands (green to dark red)
    band_defs = [
        (85, 100, "#dcfce7"),  # good - green
        (70, 85, "#ecfccb"),   # satisfactory - yellow-green
        (55, 70, "#fef9c3"),   # fair - yellow
        (40, 55, "#ffedd5"),   # poor - orange
        (25, 40, "#fee2e2"),   # very poor - red
        (0, 25, "#fecaca"),    # failed - dark red
    ]
    for band_lo, band_hi, band_clr in band_defs:
        y0 = margin_bottom + (band_lo / 100.0) * plot_h
        y1 = margin_bottom + (band_hi / 100.0) * plot_h
        pci_chart.add(Rect(
            margin_left, y0, plot_w, y1 - y0,
            fillColor=HexColor(band_clr), strokeColor=None, strokeWidth=0,
        ))

    # Axes
    pci_chart.add(Line(margin_left, margin_bottom, margin_left, margin_bottom + plot_h,
                        strokeColor=HexColor("#94a3b8"), strokeWidth=0.5))
    pci_chart.add(Line(margin_left, margin_bottom, margin_left + plot_w, margin_bottom,
                        strokeColor=HexColor("#94a3b8"), strokeWidth=0.5))

    # Y-axis labels (PCI)
    for pci_val in [0, 25, 40, 55, 70, 85, 100]:
        y = margin_bottom + (pci_val / 100.0) * plot_h
        pci_chart.add(String(margin_left - 2 * mm, y - 1 * mm, str(pci_val),
                              fontSize=6, fontName=REGULAR_FONT, fillColor=HexColor("#64748b"),
                              textAnchor="end"))
        pci_chart.add(Line(margin_left, y, margin_left + plot_w, y,
                            strokeColor=HexColor("#cbd5e1"), strokeWidth=0.3))

    # X-axis labels & PCI line
    seg_list = list(segments)
    if seg_list:
        max_dist = max(s.end_km for s in seg_list) if seg_list else 1.0
        if max_dist == 0:
            max_dist = 1.0

        # X-axis tick labels (distance in km)
        num_ticks = min(10, len(seg_list))
        for i_tick in range(num_ticks + 1):
            km_val = (i_tick / num_ticks) * max_dist
            x = margin_left + (km_val / max_dist) * plot_w
            pci_chart.add(String(x, margin_bottom - 4 * mm, f"{km_val:.1f}",
                                  fontSize=5.5, fontName=REGULAR_FONT,
                                  fillColor=HexColor("#64748b"), textAnchor="middle"))

        # Draw PCI line connecting segment midpoints
        points = []
        for seg in seg_list:
            mid_km = (seg.start_km + seg.end_km) / 2.0
            pci_val = seg.pci_score if seg.pci_score is not None else 0
            x = margin_left + (mid_km / max_dist) * plot_w
            y = margin_bottom + (min(max(pci_val, 0), 100) / 100.0) * plot_h
            points.append(x)
            points.append(y)

        if len(points) >= 4:
            pci_chart.add(PolyLine(points, strokeColor=HexColor("#1e40af"),
                                    strokeWidth=1.5))

        # Draw dots at each segment point
        from reportlab.graphics.shapes import Circle
        for i_pt in range(0, len(points), 2):
            x_pt, y_pt = points[i_pt], points[i_pt + 1]
            seg_obj = seg_list[i_pt // 2]
            dot_clr = CONDITION_COLORS.get(seg_obj.condition_rating, "#1e40af")
            pci_chart.add(Circle(x_pt, y_pt, 1.5,
                                  fillColor=HexColor(dot_clr), strokeColor=None))

    # Axis titles
    pci_chart.add(String(margin_left + plot_w / 2, 1 * mm, _("Distance (km)"),
                          fontSize=7, fontName=BOLD_FONT,
                          fillColor=HexColor("#334155"), textAnchor="middle"))
    pci_chart.add(String(2 * mm, margin_bottom + plot_h / 2, "PCI",
                          fontSize=7, fontName=BOLD_FONT,
                          fillColor=HexColor("#334155"), textAnchor="middle"))

    story.append(pci_chart)
    story.append(Spacer(1, 6 * mm))

    # ── Top 10 Worst Segments Table ──
    story.append(Paragraph(_("Top 10 Worst Segments"), h3_style))
    worst = list(segments.order_by("pci_score")[:10])
    if worst:
        worst_header = [_("Seg #"), "PCI", _("Condition"), _("Defects"), _("Location (km)")]
        worst_rows = [worst_header]
        for seg in worst:
            worst_rows.append([
                str(seg.segment_index),
                f"{seg.pci_score:.1f}" if seg.pci_score is not None else "—",
                _rating_label(seg.condition_rating),
                str(seg.defect_count),
                f"{seg.start_km:.2f} - {seg.end_km:.2f}",
            ])

        wt = Table(worst_rows, colWidths=[20 * mm, 20 * mm, 35 * mm, 25 * mm, 35 * mm])
        wt.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, 0), BOLD_FONT),
            ("FONTNAME", (0, 1), (-1, -1), REGULAR_FONT),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("BACKGROUND", (0, 0), (-1, 0), HexColor("#fef2f2")),
            ("TEXTCOLOR", (0, 0), (-1, 0), HexColor("#991b1b")),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("LINEBELOW", (0, 0), (-1, 0), 1, HexColor("#fecaca")),
            ("LINEBELOW", (0, 1), (-1, -1), 0.5, HexColor("#e2e8f0")),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        story.append(wt)
    else:
        story.append(Paragraph(_("No segments recorded."), body_style))

    story.append(Spacer(1, 6 * mm))

    # ── PCI History Section ──
    # Query sibling sessions: same road_name, same user, status=READY
    history_sessions = []
    if session.road_name:
        history_sessions = list(
            Session.objects.filter(
                road_name=session.road_name,
                user=session.user,
                status=Session.Status.READY,
            ).order_by("start_time")
        )

    if len(history_sessions) > 1:
        story.append(Paragraph(_("PCI History — Survey Trend"), h2_style))
        story.append(Paragraph(
            ngettext(
                "Historical surveys for <b>%(road)s</b> (%(count)d survey found).",
                "Historical surveys for <b>%(road)s</b> (%(count)d surveys found).",
                len(history_sessions),
            ) % {"road": session.road_name, "count": len(history_sessions)},
            body_style,
        ))
        story.append(Spacer(1, 4 * mm))

        # History bar chart
        hist_chart_w = 160 * mm
        bar_area_h = 55 * mm
        hist_margin_left = 14 * mm
        hist_margin_bottom = 14 * mm
        hist_margin_top = 6 * mm
        hist_margin_right = 4 * mm
        hist_plot_w = hist_chart_w - hist_margin_left - hist_margin_right
        hist_plot_h = bar_area_h - hist_margin_bottom - hist_margin_top

        hist_drawing = Drawing(hist_chart_w, bar_area_h)

        # Background
        hist_drawing.add(Rect(hist_margin_left, hist_margin_bottom,
                               hist_plot_w, hist_plot_h,
                               fillColor=HexColor("#f8fafc"), strokeColor=HexColor("#e2e8f0"),
                               strokeWidth=0.5))

        # Y-axis gridlines and labels
        for pci_val in [0, 25, 50, 75, 100]:
            y = hist_margin_bottom + (pci_val / 100.0) * hist_plot_h
            hist_drawing.add(Line(hist_margin_left, y, hist_margin_left + hist_plot_w, y,
                                   strokeColor=HexColor("#e2e8f0"), strokeWidth=0.3))
            hist_drawing.add(String(hist_margin_left - 2 * mm, y - 1 * mm, str(pci_val),
                                     fontSize=6, fontName=REGULAR_FONT,
                                     fillColor=HexColor("#64748b"), textAnchor="end"))

        n_bars = len(history_sessions)
        bar_gap = hist_plot_w / n_bars
        bar_width = min(bar_gap * 0.6, 18 * mm)

        for idx, hist_sess in enumerate(history_sessions):
            pci_val = hist_sess.avg_pci or 0
            bar_h = (min(max(pci_val, 0), 100) / 100.0) * hist_plot_h
            x = hist_margin_left + idx * bar_gap + (bar_gap - bar_width) / 2
            y = hist_margin_bottom

            bar_clr = CONDITION_COLORS.get(hist_sess.condition_rating, "#3b82f6")
            hist_drawing.add(Rect(x, y, bar_width, bar_h,
                                   fillColor=HexColor(bar_clr), strokeColor=None))

            # PCI value on top of bar
            hist_drawing.add(String(x + bar_width / 2, y + bar_h + 1 * mm,
                                     f"{pci_val:.0f}",
                                     fontSize=6, fontName=BOLD_FONT,
                                     fillColor=HexColor("#0f172a"), textAnchor="middle"))

            # Date label below bar
            date_str = hist_sess.start_time.strftime("%Y-%m-%d") if hist_sess.start_time else "—"
            hist_drawing.add(String(x + bar_width / 2, hist_margin_bottom - 5 * mm,
                                     date_str, fontSize=5, fontName=REGULAR_FONT,
                                     fillColor=HexColor("#64748b"), textAnchor="middle"))

            # Mark current session
            if hist_sess.pk == session.pk:
                hist_drawing.add(String(x + bar_width / 2, hist_margin_bottom - 9 * mm,
                                         _("(current)"), fontSize=5, fontName=BOLD_FONT,
                                         fillColor=HexColor("#3b82f6"), textAnchor="middle"))

        # Axis title
        hist_drawing.add(String(hist_margin_left + hist_plot_w / 2, 1 * mm,
                                 _("Survey Date"),
                                 fontSize=7, fontName=BOLD_FONT,
                                 fillColor=HexColor("#334155"), textAnchor="middle"))

        story.append(hist_drawing)
        story.append(Spacer(1, 4 * mm))

        # History table
        hist_header = [_("Date"), _("Avg PCI"), _("Distance (km)"), _("Defects"), _("Condition")]
        hist_rows = [hist_header]
        for hist_sess in history_sessions:
            hist_rows.append([
                hist_sess.start_time.strftime("%Y-%m-%d") if hist_sess.start_time else "—",
                f"{hist_sess.avg_pci:.1f}" if hist_sess.avg_pci is not None else "—",
                f"{hist_sess.distance_km:.2f}" if hist_sess.distance_km else "—",
                str(hist_sess.total_defects),
                _rating_label(hist_sess.condition_rating),
            ])

        ht = Table(hist_rows, colWidths=[30 * mm, 25 * mm, 30 * mm, 25 * mm, 35 * mm])
        ht_style_cmds = [
            ("FONTNAME", (0, 0), (-1, 0), BOLD_FONT),
            ("FONTNAME", (0, 1), (-1, -1), REGULAR_FONT),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("BACKGROUND", (0, 0), (-1, 0), HexColor("#eff6ff")),
            ("TEXTCOLOR", (0, 0), (-1, 0), HexColor("#1e40af")),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("LINEBELOW", (0, 0), (-1, 0), 1, HexColor("#bfdbfe")),
            ("LINEBELOW", (0, 1), (-1, -1), 0.3, HexColor("#e2e8f0")),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]
        # Highlight the current session row
        for row_idx, hist_sess in enumerate(history_sessions, start=1):
            if hist_sess.pk == session.pk:
                ht_style_cmds.append(("BACKGROUND", (0, row_idx), (-1, row_idx), HexColor("#dbeafe")))
                ht_style_cmds.append(("FONTNAME", (0, row_idx), (-1, row_idx), BOLD_FONT))
        ht.setStyle(TableStyle(ht_style_cmds))
        story.append(ht)
        story.append(Spacer(1, 4 * mm))

        # Trend note
        first_pci = history_sessions[0].avg_pci or 0
        last_pci = history_sessions[-1].avg_pci or 0
        n_surveys = len(history_sessions)
        if last_pci > first_pci:
            trend_template = ngettext(
                "Trend: PCI improved from %(first)s to %(last)s over %(count)d survey.",
                "Trend: PCI improved from %(first)s to %(last)s over %(count)d surveys.",
                n_surveys,
            )
        elif last_pci < first_pci:
            trend_template = ngettext(
                "Trend: PCI declined from %(first)s to %(last)s over %(count)d survey.",
                "Trend: PCI declined from %(first)s to %(last)s over %(count)d surveys.",
                n_surveys,
            )
        else:
            trend_template = ngettext(
                "Trend: PCI remained stable from %(first)s to %(last)s over %(count)d survey.",
                "Trend: PCI remained stable from %(first)s to %(last)s over %(count)d surveys.",
                n_surveys,
            )

        trend_style = ParagraphStyle(
            "Trend", parent=styles["Normal"],
            fontSize=9, leading=13, textColor=HexColor("#1e40af"),
            fontName=BOLD_FONT,
        )
        story.append(Paragraph(
            trend_template % {"first": f"{first_pci:.1f}", "last": f"{last_pci:.1f}", "count": n_surveys},
            trend_style,
        ))

    story.append(Spacer(1, 4 * mm))

    # ═══════════════════════════════════════════════════════════════════
    # PAGE 3: DEFECT INVENTORY
    # ═══════════════════════════════════════════════════════════════════
    story.append(PageBreak())
    story.append(Paragraph(_("Defect Inventory"), h2_style))

    # By type
    story.append(Paragraph(_("Defects by Type"), h3_style))
    if type_counts:
        type_header = [_("Defect Type"), _("Count"), _("Percentage")]
        type_rows = [type_header]
        for name, cnt in sorted(type_counts.items(), key=lambda x: -x[1]):
            pct = cnt / total_detections * 100 if total_detections else 0
            type_rows.append([_(name), str(cnt), f"{pct:.1f}%"])

        tt = Table(type_rows, colWidths=[60 * mm, 25 * mm, 30 * mm])
        tt.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, 0), BOLD_FONT),
            ("FONTNAME", (0, 1), (-1, -1), REGULAR_FONT),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BACKGROUND", (0, 0), (-1, 0), HexColor("#f1f5f9")),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("LINEBELOW", (0, 0), (-1, 0), 1, HexColor("#cbd5e1")),
            ("LINEBELOW", (0, 1), (-1, -1), 0.5, HexColor("#e2e8f0")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        story.append(tt)
    else:
        story.append(Paragraph(_("No defects detected."), body_style))

    story.append(Spacer(1, 6 * mm))

    # By severity
    story.append(Paragraph(_("Defects by Severity"), h3_style))
    sev_header = [_("Severity"), _("Count"), _("Percentage"), ""]
    sev_rows = [sev_header]
    for sev in ["critical", "high", "medium", "low"]:
        cnt = severity_counts.get(sev, 0)
        if cnt > 0:
            pct = cnt / total_detections * 100 if total_detections else 0
            bar = chr(9608) * max(1, int(pct / 2))
            sev_rows.append([_severity_label(sev), str(cnt), f"{pct:.1f}%", bar])

    if len(sev_rows) > 1:
        svt = Table(sev_rows, colWidths=[42 * mm, 26 * mm, 22 * mm, 70 * mm])
        svt.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, 0), BOLD_FONT),
            ("FONTNAME", (0, 1), (-1, -1), REGULAR_FONT),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("BACKGROUND", (0, 0), (-1, 0), HexColor("#f1f5f9")),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("LINEBELOW", (0, 0), (-1, 0), 1, HexColor("#cbd5e1")),
            ("LINEBELOW", (0, 1), (-1, -1), 0.5, HexColor("#e2e8f0")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        for sev, clr in SEVERITY_COLORS.items():
            if severity_counts.get(sev, 0) > 0:
                idx = [r[0] for r in sev_rows].index(_severity_label(sev))
                svt.setStyle(TableStyle([
                    ("TEXTCOLOR", (0, idx), (0, idx), HexColor(clr)),
                    ("FONTNAME", (0, idx), (0, idx), BOLD_FONT),
                    ("TEXTCOLOR", (3, idx), (3, idx), HexColor(clr)),
                ]))
        story.append(svt)

    # ═══════════════════════════════════════════════════════════════════
    # PAGE 4: RECOMMENDATIONS
    # ═══════════════════════════════════════════════════════════════════
    story.append(PageBreak())
    story.append(Paragraph(_("Maintenance Recommendations"), h2_style))

    recs = _generate_recommendations(avg_pci, severity_counts, type_counts, distance)
    for rec in recs:
        story.append(Paragraph(f"<bullet>&bull;</bullet> {rec}", body_style))
        story.append(Spacer(1, 2 * mm))

    story.append(Spacer(1, 10 * mm))

    # Methodology note
    story.append(Paragraph(_("Methodology"), h3_style))
    story.append(Paragraph(
        _(
            "This assessment was conducted using the ZaminTwin.ai automated road inspection system. "
            "A vehicle-mounted camera captures road surface imagery while GPS tracks the route. "
            "An AI model (YOLO-based, running on NVIDIA Jetson) detects pavement defects in real-time. "
            "The Pavement Condition Index (PCI) is calculated per 100-meter road segment based on "
            "defect type, severity, and density, following principles from ASTM D6433. "
            "PCI ranges from 0 (failed) to 100 (perfect condition)."
        ),
        body_style,
    ))

    story.append(Spacer(1, 8 * mm))

    # PCI Scale reference
    story.append(Paragraph(_("PCI Rating Scale"), h3_style))
    scale_data = [
        [_("Score Range"), _("Rating"), _("Action")],
        ["85 - 100", _rating_label("good"), _("Routine maintenance only")],
        ["70 - 84", _rating_label("satisfactory"), _("Preventive maintenance (1-2 years)")],
        ["55 - 69", _rating_label("fair"), _("Crack sealing and patching needed")],
        ["40 - 54", _rating_label("poor"), _("Rehabilitation / overlay required")],
        ["25 - 39", _rating_label("very_poor"), _("Major rehabilitation needed")],
        ["0 - 24", _rating_label("failed"), _("Full reconstruction required")],
    ]
    sct = Table(scale_data, colWidths=[34 * mm, 42 * mm, 94 * mm])
    sct.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), BOLD_FONT),
        ("FONTNAME", (0, 1), (-1, -1), REGULAR_FONT),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("BACKGROUND", (0, 0), (-1, 0), HexColor("#f1f5f9")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, 0), 1, HexColor("#cbd5e1")),
        ("LINEBELOW", (0, 1), (-1, -1), 0.3, HexColor("#e2e8f0")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    # Color the rating column
    rating_colors = ["#22c55e", "#84cc16", "#eab308", "#f97316", "#ef4444", "#991b1b"]
    for i, clr in enumerate(rating_colors):
        sct.setStyle(TableStyle([
            ("TEXTCOLOR", (1, i + 1), (1, i + 1), HexColor(clr)),
            ("FONTNAME", (1, i + 1), (1, i + 1), BOLD_FONT),
        ]))
    story.append(sct)

    story.append(Spacer(1, 15 * mm))

    # Footer
    story.append(Paragraph(
        _(
            "Report generated by ZaminTwin.ai Road Inspection Platform. "
            "Session: %(session)s | PCI evaluation follows ASTM D6433 methodology."
        ) % {"session": session.session_id},
        small_style,
    ))

    # ── Build & Return ───────────────────────────────────────────────
    doc.build(story)
    buf.seek(0)

    response = HttpResponse(buf.read(), content_type="application/pdf")
    filename = f"ZaminTwin_Report_{session.session_id}_{datetime.now().strftime('%Y%m%d')}.pdf"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def _generate_recommendations(avg_pci, severity_counts, type_counts, distance_km):
    """Generate maintenance recommendations based on assessment data."""
    recs = []
    pci = {"pci": f"{avg_pci:.1f}"}

    # Overall condition recommendation
    if avg_pci >= 85:
        recs.append(_(
            "Overall road condition is Good (PCI %(pci)s). "
            "Continue routine maintenance and periodic monitoring."
        ) % pci)
    elif avg_pci >= 70:
        recs.append(_(
            "Overall road condition is Satisfactory (PCI %(pci)s). "
            "Schedule preventive maintenance within 1-2 years to prevent further deterioration."
        ) % pci)
    elif avg_pci >= 55:
        recs.append(_(
            "Overall road condition is Fair (PCI %(pci)s). "
            "Crack sealing and localized patching are recommended within 6-12 months."
        ) % pci)
    elif avg_pci >= 40:
        recs.append(_(
            "Overall road condition is Poor (PCI %(pci)s). "
            "Rehabilitation is needed. Consider asphalt overlay for the most affected sections."
        ) % pci)
    else:
        recs.append(_(
            "Overall road condition is Very Poor to Failed (PCI %(pci)s). "
            "Major rehabilitation or full reconstruction is urgently required."
        ) % pci)

    # Specific defect recommendations
    potholes = sum(v for k, v in type_counts.items() if "pothole" in k.lower())
    cracks = sum(v for k, v in type_counts.items() if "crack" in k.lower())

    if potholes > 0:
        density = potholes / distance_km if distance_km > 0 else 0
        recs.append(ngettext(
            "%(count)d pothole detected (%(density)s per km). "
            "Priority patching recommended for all critical and high severity potholes.",
            "%(count)d potholes detected (%(density)s per km). "
            "Priority patching recommended for all critical and high severity potholes.",
            potholes,
        ) % {"count": potholes, "density": f"{density:.1f}"})

    if cracks > 0:
        recs.append(ngettext(
            "%(count)d crack defect detected across the surveyed route. "
            "Crack sealing should be applied to prevent water infiltration and further deterioration.",
            "%(count)d crack defects detected across the surveyed route. "
            "Crack sealing should be applied to prevent water infiltration and further deterioration.",
            cracks,
        ) % {"count": cracks})

    # Severity-based recommendations
    critical = severity_counts.get("critical", 0)
    if critical > 0:
        recs.append(ngettext(
            "%(count)d critical-severity defect requires immediate attention. "
            "It poses a safety hazard and should be addressed within 30 days.",
            "%(count)d critical-severity defects require immediate attention. "
            "These pose safety hazards and should be addressed within 30 days.",
            critical,
        ) % {"count": critical})

    high = severity_counts.get("high", 0)
    if high > 5:
        recs.append(ngettext(
            "%(count)d high-severity defect detected. "
            "Schedule repair within the next maintenance cycle (60-90 days).",
            "%(count)d high-severity defects detected. "
            "Schedule repair within the next maintenance cycle (60-90 days).",
            high,
        ) % {"count": high})

    # General
    recs.append(_(
        "Re-survey this road section in 3-6 months to track condition changes "
        "and verify the effectiveness of any maintenance actions taken."
    ))

    return recs


@login_required
def multi_session_pdf_report(request):
    """Generate a combined PDF report for multiple selected sessions."""
    ids_str = request.GET.get("ids", "")
    try:
        session_ids = [int(x) for x in ids_str.split(",") if x.strip()]
    except ValueError:
        return HttpResponse(_("Invalid session IDs"), status=400)

    if not session_ids:
        return HttpResponse(_("No sessions specified"), status=400)

    sessions_qs = Session.objects.filter(
        pk__in=session_ids, user=request.user, status=Session.Status.READY,
    ).order_by("road_name", "-start_time")

    if not sessions_qs.exists():
        return HttpResponse(_("No valid sessions found"), status=404)

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.lib.colors import HexColor, black, white
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
            PageBreak,
        )
        from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
        from reportlab.graphics.shapes import Drawing, Rect, String
    except ImportError:
        return HttpResponse(_("reportlab is not installed"), status=500)

    sessions_list = list(sessions_qs)

    # ── Aggregate stats ──
    total_dist = sum(s.distance_km for s in sessions_list)
    total_defects = sum(s.total_defects for s in sessions_list)
    pcis = [s.avg_pci for s in sessions_list if s.avg_pci is not None]
    avg_pci = sum(pcis) / len(pcis) if pcis else 0
    overall_rating, _overall_color = _get_overall_rating(avg_pci)

    # ── Build PDF ──
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=25 * mm, bottomMargin=20 * mm,
    )
    story = []
    styles = unicode_stylesheet()

    brand_color = HexColor("#0f172a")
    accent_color = HexColor("#3b82f6")

    title_style = ParagraphStyle(
        "MTitle", parent=styles["Title"],
        fontSize=24, leading=30, spaceAfter=4, textColor=brand_color,
        fontName=BOLD_FONT,
    )
    subtitle_style = ParagraphStyle(
        "MSubtitle", parent=styles["Normal"],
        fontSize=10, textColor=HexColor("#64748b"), spaceAfter=20,
    )
    h2_style = ParagraphStyle(
        "MH2", parent=styles["Heading2"],
        fontSize=14, spaceAfter=8, spaceBefore=16,
        textColor=brand_color, fontName=BOLD_FONT,
    )
    h3_style = ParagraphStyle(
        "MH3", parent=styles["Heading3"],
        fontSize=11, spaceAfter=6, spaceBefore=12,
        textColor=HexColor("#334155"), fontName=BOLD_FONT,
    )
    body_style = ParagraphStyle(
        "MBody", parent=styles["Normal"],
        fontSize=9, leading=13, textColor=HexColor("#334155"),
    )
    small_style = ParagraphStyle(
        "MSmall", parent=styles["Normal"],
        fontSize=7.5, leading=10, textColor=HexColor("#94a3b8"),
    )

    # ═══════════════════════════════════════════════════════════════════
    # PAGE 1: COVER + NETWORK SUMMARY
    # ═══════════════════════════════════════════════════════════════════
    story.append(Spacer(1, 15 * mm))
    story.append(Paragraph("ZaminTwin.ai", ParagraphStyle(
        "MBrand", parent=styles["Normal"],
        fontSize=12, textColor=accent_color, fontName=BOLD_FONT,
        spaceAfter=2,
    )))
    story.append(Paragraph(_("Multi-Session Road Assessment Report"), title_style))
    story.append(Paragraph(
        _("Sessions: %(count)s &nbsp;|&nbsp; Generated: %(generated)s &nbsp;|&nbsp; Inspector: %(inspector)s") % {
            "count": len(sessions_list),
            "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "inspector": request.user.get_full_name() or request.user.username,
        },
        subtitle_style,
    ))

    # Overall stats box
    pci_color = CONDITION_COLORS.get(overall_rating, "#64748b")
    pci_drawing = Drawing(170 * mm, 28 * mm)
    pci_drawing.add(Rect(0, 0, 170 * mm, 28 * mm, rx=4 * mm,
                         fillColor=HexColor(pci_color), fillOpacity=0.1,
                         strokeColor=HexColor(pci_color), strokeWidth=1))
    pci_drawing.add(String(15 * mm, 8 * mm,
                           _("Average PCI %(pci)s  —  %(rating)s") % {
                               "pci": f"{avg_pci:.1f}", "rating": _rating_label(overall_rating),
                           },
                           fontSize=18, fontName=BOLD_FONT,
                           fillColor=HexColor(pci_color)))
    pci_drawing.add(String(165 * mm, 8 * mm,
                           _("%(distance)s km total") % {"distance": f"{total_dist:.1f}"},
                           fontSize=10, fontName=REGULAR_FONT,
                           fillColor=HexColor("#64748b"), textAnchor="end"))
    story.append(pci_drawing)
    story.append(Spacer(1, 8 * mm))

    # Network summary table
    story.append(Paragraph(_("Network Summary"), h2_style))
    summary_data = [
        [_("Total Sessions"), str(len(sessions_list))],
        [_("Total Distance"), f"{total_dist:.1f} " + _("km")],
        [_("Average PCI"), f"{avg_pci:.1f} ({_rating_label(overall_rating)})"],
        [_("Total Defects"), str(total_defects)],
        [_("Defects per km"), f"{(total_defects / total_dist):.1f}" if total_dist > 0 else "—"],
    ]
    t = Table(summary_data, colWidths=[62 * mm, 108 * mm])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), BOLD_FONT),
        ("FONTNAME", (1, 0), (1, -1), REGULAR_FONT),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), HexColor("#64748b")),
        ("TEXTCOLOR", (1, 0), (1, -1), brand_color),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, HexColor("#e2e8f0")),
    ]))
    story.append(t)
    story.append(Spacer(1, 8 * mm))

    # Session comparison table
    story.append(Paragraph(_("Session Comparison"), h2_style))
    comp_header = [_("Road Name"), _("Date"), _("Distance"), "PCI", _("Condition"), _("Defects")]
    comp_rows = [comp_header]
    for s in sessions_list:
        comp_rows.append([
            s.display_name[:30],
            s.start_time.strftime("%Y-%m-%d") if s.start_time else "—",
            f"{s.distance_km:.1f} " + _("km"),
            f"{s.avg_pci:.1f}" if s.avg_pci is not None else "—",
            _rating_label(s.condition_rating),
            str(s.total_defects),
        ])

    ct = Table(comp_rows, colWidths=[45 * mm, 25 * mm, 20 * mm, 18 * mm, 30 * mm, 20 * mm])
    comp_style = [
        ("FONTNAME", (0, 0), (-1, 0), BOLD_FONT),
        ("FONTNAME", (0, 1), (-1, -1), REGULAR_FONT),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("BACKGROUND", (0, 0), (-1, 0), HexColor("#0f172a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), white),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("LINEBELOW", (0, 0), (-1, 0), 1, HexColor("#334155")),
        ("LINEBELOW", (0, 1), (-1, -1), 0.3, HexColor("#e2e8f0")),
        ("ALIGN", (2, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
    # Color PCI cells
    for i, s in enumerate(sessions_list, start=1):
        clr = CONDITION_COLORS.get(s.condition_rating, "#64748b")
        comp_style.append(("TEXTCOLOR", (3, i), (3, i), HexColor(clr)))
        comp_style.append(("FONTNAME", (3, i), (3, i), BOLD_FONT))
        if i % 2 == 0:
            comp_style.append(("BACKGROUND", (0, i), (-1, i), HexColor("#f8fafc")))
    ct.setStyle(TableStyle(comp_style))
    story.append(ct)

    # ═══════════════════════════════════════════════════════════════════
    # PER-SESSION PAGES
    # ═══════════════════════════════════════════════════════════════════
    for s in sessions_list:
        story.append(PageBreak())

        segs = RoadSegment.objects.filter(session=s).order_by("segment_index")
        dets = Detection.objects.filter(session=s, is_duplicate=False).order_by("distance_km")

        # Session header
        story.append(Paragraph(s.display_name, h2_style))
        pci_val = s.avg_pci or 0
        cond = s.condition_rating or "unknown"
        s_color = CONDITION_COLORS.get(cond, "#64748b")

        # Session stats
        s_data = [
            [_("Date"), s.start_time.strftime("%Y-%m-%d %H:%M") if s.start_time else "—"],
            [_("Distance"), f"{s.distance_km:.1f} " + _("km")],
            [_("PCI Score"), f"{pci_val:.1f} ({_rating_label(cond)})"],
            [_("Segments"), str(segs.count())],
            [_("Total Defects"), str(dets.count())],
            [_("Defects/km"), f"{(dets.count() / s.distance_km):.1f}" if s.distance_km > 0 else "—"],
        ]
        st = Table(s_data, colWidths=[52 * mm, 108 * mm])
        st.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (0, -1), BOLD_FONT),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("TEXTCOLOR", (0, 0), (0, -1), HexColor("#64748b")),
            ("TEXTCOLOR", (1, 0), (1, -1), brand_color),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("LINEBELOW", (0, 0), (-1, -1), 0.5, HexColor("#e2e8f0")),
        ]))
        story.append(st)
        story.append(Spacer(1, 6 * mm))

        # Defect type breakdown
        type_counts = {}
        sev_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for d in dets:
            name = _defect_name(d.defect_type)
            type_counts[name] = type_counts.get(name, 0) + 1
            if d.severity in sev_counts:
                sev_counts[d.severity] += 1

        if type_counts:
            story.append(Paragraph(_("Defect Breakdown"), h3_style))
            dt_header = [_("Defect Type"), _("Count"), _("Severity Distribution")]
            dt_rows = [dt_header]
            for name, cnt in sorted(type_counts.items(), key=lambda x: -x[1]):
                dt_rows.append([_(name), str(cnt), ""])
            dtt = Table(dt_rows, colWidths=[50 * mm, 20 * mm, 80 * mm])
            dtt.setStyle(TableStyle([
                ("FONTNAME", (0, 0), (-1, 0), BOLD_FONT),
                ("FONTNAME", (0, 1), (-1, -1), REGULAR_FONT),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("BACKGROUND", (0, 0), (-1, 0), HexColor("#f1f5f9")),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("LINEBELOW", (0, 0), (-1, 0), 1, HexColor("#cbd5e1")),
                ("LINEBELOW", (0, 1), (-1, -1), 0.3, HexColor("#e2e8f0")),
            ]))
            story.append(dtt)
            story.append(Spacer(1, 4 * mm))

        # Worst segments (top 5)
        worst = list(segs.order_by("pci_score")[:5])
        if worst:
            story.append(Paragraph(_("Critical Segments"), h3_style))
            w_header = [_("Seg"), "PCI", _("Condition"), _("Defects"), _("Location")]
            w_rows = [w_header]
            for seg in worst:
                w_rows.append([
                    str(seg.segment_index),
                    f"{seg.pci_score:.1f}" if seg.pci_score is not None else "—",
                    _rating_label(seg.condition_rating),
                    str(seg.defect_count),
                    f"{seg.start_km:.2f}–{seg.end_km:.2f} " + _("km"),
                ])
            wt = Table(w_rows, colWidths=[15 * mm, 18 * mm, 35 * mm, 20 * mm, 30 * mm])
            wt.setStyle(TableStyle([
                ("FONTNAME", (0, 0), (-1, 0), BOLD_FONT),
                ("FONTNAME", (0, 1), (-1, -1), REGULAR_FONT),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("BACKGROUND", (0, 0), (-1, 0), HexColor("#fef2f2")),
                ("TEXTCOLOR", (0, 0), (-1, 0), HexColor("#991b1b")),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("LINEBELOW", (0, 0), (-1, 0), 1, HexColor("#fecaca")),
                ("LINEBELOW", (0, 1), (-1, -1), 0.3, HexColor("#e2e8f0")),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ]))
            story.append(wt)

    # ═══════════════════════════════════════════════════════════════════
    # FINAL PAGE: RECOMMENDATIONS
    # ═══════════════════════════════════════════════════════════════════
    story.append(PageBreak())
    story.append(Paragraph(_("Maintenance Recommendations"), h2_style))

    # Aggregate recommendations
    total_type_counts = {}
    total_sev_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for s in sessions_list:
        for d in Detection.objects.filter(session=s, is_duplicate=False):
            name = _defect_name(d.defect_type)
            total_type_counts[name] = total_type_counts.get(name, 0) + 1
            if d.severity in total_sev_counts:
                total_sev_counts[d.severity] += 1

    recs = _generate_recommendations(avg_pci, total_sev_counts, total_type_counts, total_dist)
    for rec in recs:
        story.append(Paragraph(f"<bullet>&bull;</bullet> {rec}", body_style))
        story.append(Spacer(1, 2 * mm))

    # Priority roads
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph(_("Priority Roads for Maintenance"), h3_style))
    priority = sorted(sessions_list, key=lambda s: s.avg_pci or 100)[:10]
    pr_header = [_("Priority"), _("Road"), "PCI", _("Condition"), _("Action Needed")]
    pr_rows = [pr_header]
    for i, s in enumerate(priority, 1):
        pci_val = s.avg_pci or 0
        cond = _rating_label(s.condition_rating or "unknown")
        if pci_val >= 70:
            action = _("Preventive maintenance")
        elif pci_val >= 55:
            action = _("Crack sealing & patching")
        elif pci_val >= 40:
            action = _("Rehabilitation / overlay")
        elif pci_val >= 25:
            action = _("Major rehabilitation")
        else:
            action = _("Full reconstruction")
        pr_rows.append([str(i), s.display_name[:25], f"{pci_val:.1f}", cond, action])

    pt = Table(pr_rows, colWidths=[24 * mm, 42 * mm, 14 * mm, 36 * mm, 54 * mm])
    pt_style = [
        ("FONTNAME", (0, 0), (-1, 0), BOLD_FONT),
        ("FONTNAME", (0, 1), (-1, -1), REGULAR_FONT),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("BACKGROUND", (0, 0), (-1, 0), HexColor("#0f172a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), white),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("LINEBELOW", (0, 0), (-1, 0), 1, HexColor("#334155")),
        ("LINEBELOW", (0, 1), (-1, -1), 0.3, HexColor("#e2e8f0")),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (2, 0), (2, -1), "CENTER"),
    ]
    for i, s in enumerate(priority, 1):
        clr = CONDITION_COLORS.get(s.condition_rating, "#64748b")
        pt_style.append(("TEXTCOLOR", (2, i), (2, i), HexColor(clr)))
        pt_style.append(("FONTNAME", (2, i), (2, i), BOLD_FONT))
    pt.setStyle(TableStyle(pt_style))
    story.append(pt)

    story.append(Spacer(1, 15 * mm))
    story.append(Paragraph(
        _("Report generated by ZaminTwin.ai Road Inspection Platform. Sessions: %(count)s | %(date)s") % {
            "count": len(sessions_list),
            "date": datetime.now().strftime("%Y-%m-%d"),
        },
        small_style,
    ))

    # ── Build & Return ──
    doc.build(story)
    buf.seek(0)

    response = HttpResponse(buf.read(), content_type="application/pdf")
    filename = f"ZaminTwin_MultiReport_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def _get_overall_rating(pci):
    """Get condition rating and color from PCI score."""
    for threshold, rating, color in [
        (85, "good", "#22c55e"), (70, "satisfactory", "#84cc16"),
        (55, "fair", "#eab308"), (40, "poor", "#f97316"),
        (25, "very_poor", "#ef4444"), (0, "failed", "#991b1b"),
    ]:
        if pci >= threshold:
            return rating, color
    return "failed", "#991b1b"
