"""
Views for session-based road inspection.
"""
import json
import os
from collections import defaultdict

from django.utils.formats import date_format
from django.utils.translation import gettext as _, gettext_lazy
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST
from django.utils import timezone

from .models import Session, Detection, RoadSegment
from .ingest import ingest_session, IngestError


# ============================================================================
# Defect type display names
# ============================================================================
DEFECT_DISPLAY_NAMES = {
    "D00": gettext_lazy("Longitudinal Crack"),
    "D10": gettext_lazy("Transverse Crack"),
    "D20": gettext_lazy("Alligator Crack"),
    "D40": gettext_lazy("Pothole"),
    "D50": gettext_lazy("Pothole"),
    "d00": gettext_lazy("Longitudinal Crack"),
    "d10": gettext_lazy("Transverse Crack"),
    "d20": gettext_lazy("Alligator Crack"),
    "d40": gettext_lazy("Pothole"),
    "d50": gettext_lazy("Pothole"),
    "pothole": gettext_lazy("Pothole"),
    "Pothole": gettext_lazy("Pothole"),
    "alligator_crack": gettext_lazy("Alligator Crack"),
    "Alligator Crack": gettext_lazy("Alligator Crack"),
    "longitudinal_crack": gettext_lazy("Longitudinal Crack"),
    "Longitudinal Crack": gettext_lazy("Longitudinal Crack"),
    "transverse_crack": gettext_lazy("Transverse Crack"),
    "Transverse Crack": gettext_lazy("Transverse Crack"),
    "Other Damage": gettext_lazy("Other Damage"),
    "patch": gettext_lazy("Patch/Repair"),
    "rutting": gettext_lazy("Rutting"),
    "bleeding": gettext_lazy("Bleeding"),
}


def get_defect_display_name(raw_type):
    """Convert raw defect type code to human-readable name."""
    raw = (raw_type or "").strip()
    known = (
        DEFECT_DISPLAY_NAMES.get(raw)
        or DEFECT_DISPLAY_NAMES.get(raw.lower())
        or DEFECT_DISPLAY_NAMES.get(raw.upper())
    )
    return str(known) if known else raw.replace("_", " ").title()


# ============================================================================
# Network Map — the "wow" landing page
# ============================================================================
@login_required
def city_selector(request):
    """City/project selector — shows cards for each city with sessions."""
    sessions = Session.objects.filter(
        user=request.user, status=Session.Status.READY,
    )
    # Group by city
    cities = {}
    for s in sessions:
        city = s.city or "Uncategorized"
        if city not in cities:
            cities[city] = {
                "name": city,
                "sessions": 0,
                "total_distance": 0,
                "total_defects": 0,
                "pcis": [],
                "min_lat": None, "max_lat": None,
                "min_lon": None, "max_lon": None,
            }
        c = cities[city]
        c["sessions"] += 1
        c["total_distance"] += s.distance_km
        c["total_defects"] += s.total_defects
        if s.avg_pci is not None:
            c["pcis"].append(s.avg_pci)
        # Track bounds
        for field, fn in [("min_lat", min), ("min_lon", min), ("max_lat", max), ("max_lon", max)]:
            val = getattr(s, field)
            if val is not None:
                if c[field] is None:
                    c[field] = val
                else:
                    c[field] = fn(c[field], val)

    city_list = []
    for name, data in sorted(cities.items(), key=lambda x: -x[1]["sessions"]):
        data["total_distance"] = round(data["total_distance"], 1)
        data["avg_pci"] = round(sum(data["pcis"]) / len(data["pcis"]), 1) if data["pcis"] else None
        data["slug"] = name.replace(" ", "-").lower()
        city_list.append(data)

    context = {
        "cities": city_list,
        "total_sessions": sessions.count(),
    }
    return render(request, "sessions/city_selector.html", context)


@login_required
def network_map(request):
    """Full-screen network health map — optionally filtered by city."""
    city_filter = request.GET.get("city", "")

    sessions = Session.objects.filter(
        user=request.user, status=Session.Status.READY,
    )
    if city_filter:
        sessions = sessions.filter(city=city_filter)
    sessions = sessions.order_by("-created_at")

    # Build network GeoJSON server-side (avoid extra AJAX call)
    features = []
    for session in sessions:
        for seg in session.segments.all().order_by("segment_index"):
            if not seg.track_points or len(seg.track_points) < 2:
                continue
            coordinates = [[p[1], p[0]] for p in seg.track_points]
            features.append({
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": coordinates},
                "properties": {
                    "session_id": session.pk,
                    "session_name": session.session_id,
                    "segment_index": seg.segment_index,
                    "pci_score": seg.pci_score,
                    "color": seg.color,
                    "condition_rating": seg.condition_rating,
                    "defect_count": seg.defect_count,
                },
            })

    network_geojson = {"type": "FeatureCollection", "features": features}

    # Build detection points GeoJSON
    det_features = []
    all_detections = list(Detection.objects.filter(
        session__user=request.user,
        session__status=Session.Status.READY,
        is_duplicate=False,
    ).select_related("session"))

    # Group by (session_id, frame_number) for sibling bboxes
    net_frame_map = defaultdict(list)
    for det in all_detections:
        key = (det.session_id, det.frame_number or 0)
        if det.bbox:
            net_frame_map[key].append({
                "bbox": det.bbox,
                "type": get_defect_display_name(det.defect_type),
                "raw_type": det.defect_type,
                "id": det.id,
            })

    for det in all_detections:
        key = (det.session_id, det.frame_number or 0)
        all_bboxes = net_frame_map.get(key, [])
        det_features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [det.lon, det.lat]},
            "properties": {
                "id": det.id,
                "session_id": det.session_id,
                "type": get_defect_display_name(det.defect_type),
                "raw_type": det.defect_type,
                "severity": det.severity,
                "confidence": round(det.confidence, 2),
                "distance_km": det.distance_km,
                "frame": det.frame_number,
                "thumbnail": det.thumbnail.url if det.thumbnail and str(det.thumbnail) else None,
                "bbox": det.bbox if det.bbox else None,
                "frame_bboxes": all_bboxes if len(all_bboxes) > 1 else None,
            },
        })

    detections_geojson = {"type": "FeatureCollection", "features": det_features}

    # Stats
    total_dist = sum(s.distance_km for s in sessions)
    total_defects = sum(s.total_defects for s in sessions)
    pcis = [s.avg_pci for s in sessions if s.avg_pci is not None]
    avg_pci = round(sum(pcis) / len(pcis), 1) if pcis else None

    stats = {
        "total_sessions": sessions.count(),
        "total_distance": round(total_dist, 1),
        "total_defects": total_defects,
        "avg_pci": avg_pci,
    }

    context = {
        "sessions": sessions,
        "stats": stats,
        "city_filter": city_filter,
        "network_geojson": json.dumps(network_geojson),
        "detections_geojson": json.dumps(detections_geojson),
    }
    return render(request, "sessions/network_map.html", context)


@login_required
def session_list(request):
    """Redirect to network map — the unified landing page."""
    return redirect("sessions:network_map")


@login_required
def multi_session_review(request):
    """Review multiple sessions on one page for report generation."""
    ids_str = request.GET.get("ids", "")
    try:
        session_ids = [int(x) for x in ids_str.split(",") if x.strip()]
    except ValueError:
        session_ids = []

    if not session_ids:
        return redirect("sessions:network_map")

    sessions_qs = Session.objects.filter(
        pk__in=session_ids, user=request.user, status=Session.Status.READY,
    ).order_by("road_name", "-start_time")

    if not sessions_qs.exists():
        return redirect("sessions:network_map")

    # Build per-session data
    sessions_data = []
    all_segments_features = []
    all_det_features = []

    for session in sessions_qs:
        segments = RoadSegment.objects.filter(session=session).order_by("segment_index")
        detections = Detection.objects.filter(
            session=session, is_duplicate=False,
        ).order_by("distance_km")

        # Segments GeoJSON
        for seg in segments:
            if not seg.track_points or len(seg.track_points) < 2:
                continue
            coords = [[p[1], p[0]] for p in seg.track_points]
            all_segments_features.append({
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": coords},
                "properties": {
                    "session_id": session.pk,
                    "color": seg.color,
                    "pci_score": seg.pci_score,
                    "condition_rating": seg.condition_rating,
                },
            })

        # Detection points — group by frame for sibling bboxes
        det_list = list(detections)
        mr_frame_map = defaultdict(list)
        for det in det_list:
            fn = det.frame_number or 0
            if det.bbox:
                mr_frame_map[fn].append({
                    "bbox": det.bbox,
                    "type": get_defect_display_name(det.defect_type),
                    "raw_type": det.defect_type,
                    "id": det.id,
                })
        for det in det_list:
            fn = det.frame_number or 0
            all_bboxes = mr_frame_map.get(fn, [])
            all_det_features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [det.lon, det.lat]},
                "properties": {
                    "id": det.id,
                    "session_id": session.pk,
                    "type": get_defect_display_name(det.defect_type),
                    "raw_type": det.defect_type,
                    "severity": det.severity,
                    "confidence": round(det.confidence, 2),
                    "distance_km": det.distance_km,
                    "frame": det.frame_number,
                    "thumbnail": det.thumbnail.url if det.thumbnail and str(det.thumbnail) else None,
                    "bbox": det.bbox if det.bbox else None,
                    "frame_bboxes": all_bboxes if len(all_bboxes) > 1 else None,
                },
            })

        sessions_data.append({
            "session": session,
            "detections": detections,
            "segments": segments,
            "det_count": detections.count(),
        })

    # Aggregated stats
    total_dist = sum(s.distance_km for s in sessions_qs)
    total_defects = sum(s.total_defects for s in sessions_qs)
    pcis = [s.avg_pci for s in sessions_qs if s.avg_pci is not None]
    avg_pci = round(sum(pcis) / len(pcis), 1) if pcis else None

    context = {
        "sessions_data": sessions_data,
        "session_ids": ",".join(str(s) for s in session_ids),
        "stats": {
            "count": len(sessions_data),
            "total_distance": round(total_dist, 1),
            "total_defects": total_defects,
            "avg_pci": avg_pci,
        },
        "segments_geojson": json.dumps({"type": "FeatureCollection", "features": all_segments_features}),
        "detections_geojson": json.dumps({"type": "FeatureCollection", "features": all_det_features}),
    }
    return render(request, "sessions/multi_review.html", context)


def _build_detections_json(detections, _safe_thumb):
    """Build detection JSON list with sibling bboxes for same-frame detections."""
    det_list = list(detections)
    frame_map = defaultdict(list)
    for d in det_list:
        fn = d.frame_number or 0
        if d.bbox:
            frame_map[fn].append({
                "bbox": d.bbox,
                "type": get_defect_display_name(d.defect_type),
                "raw_type": d.defect_type,
                "id": d.id,
            })

    result = []
    for d in det_list:
        fn = d.frame_number or 0
        all_bboxes = frame_map.get(fn, [])
        result.append({
            "id": d.id,
            "type": get_defect_display_name(d.defect_type),
            "raw_type": d.defect_type,
            "confidence": float(d.confidence) if d.confidence is not None else 0,
            "severity": d.severity or "medium",
            "lat": float(d.lat) if d.lat is not None else 0,
            "lon": float(d.lon) if d.lon is not None else 0,
            "distance_km": float(d.distance_km) if d.distance_km is not None else 0,
            "frame": fn,
            "verification": d.verification_status_name,
            "thumbnail": _safe_thumb(d),
            "bbox": d.bbox if d.bbox else None,
            "frame_bboxes": all_bboxes if len(all_bboxes) > 1 else None,
        })
    return result


@login_required
@ensure_csrf_cookie
def session_detail(request, session_id):
    """Session detail with map, detections, and PCI chart."""
    session = get_object_or_404(Session, pk=session_id, user=request.user)

    detections = Detection.objects.filter(
        session=session, is_duplicate=False,
    ).order_by("distance_km")

    segments = RoadSegment.objects.filter(session=session).order_by("segment_index")

    # Filter detections
    dtype = request.GET.get("type")
    if dtype:
        detections = detections.filter(defect_type=dtype)

    severity = request.GET.get("severity")
    if severity:
        detections = detections.filter(severity=severity)

    vstatus = request.GET.get("verification")
    if vstatus:
        status_map = {"pending": 0, "verified": 1, "rejected": 2}
        if vstatus in status_map:
            detections = detections.filter(verification_status=status_map[vstatus])

    # Defect types for filter chips (unique display names)
    raw_types = (
        Detection.objects.filter(session=session, is_duplicate=False)
        .values_list("defect_type", flat=True)
        .distinct()
    )
    seen_names = set()
    filter_chips = []
    for rt in raw_types:
        display = get_defect_display_name(rt)
        if display not in seen_names:
            seen_names.add(display)
            filter_chips.append({"raw": rt, "name": display})

    # Build safe JSON for template
    def _safe_thumb(d):
        try:
            if d.thumbnail and str(d.thumbnail):
                return d.thumbnail.url
        except Exception:
            pass
        return None

    # History: find other sessions on the same road
    history_json = "[]"
    history_segments_json = "[]"
    if session.road_name:
        siblings = Session.objects.filter(
            user=request.user,
            road_name=session.road_name,
            status=Session.Status.READY,
        ).order_by("start_time")
        if siblings.count() > 1:
            history_json = json.dumps([
                {
                    "id": s.pk,
                    "session_id": s.session_id,
                    "date": date_format(s.start_time, "M Y") if s.start_time else "—",
                    "date_full": s.start_time.strftime("%Y-%m-%d") if s.start_time else "",
                    "pci": float(s.avg_pci) if s.avg_pci is not None else None,
                    "condition": s.condition_rating or "",
                    "defects": s.total_defects,
                    "distance_km": float(s.distance_km),
                    "is_current": s.pk == session.pk,
                    "url": f"/sessions/{s.pk}/",
                }
                for s in siblings
            ])
            # Segment-level PCI per sibling for the history line chart
            history_lines = []
            for s in siblings:
                segs = RoadSegment.objects.filter(session=s).order_by("segment_index")
                history_lines.append({
                    "id": s.pk,
                    "date": date_format(s.start_time, "M Y") if s.start_time else "—",
                    "is_current": s.pk == session.pk,
                    "avg_pci": float(s.avg_pci) if s.avg_pci is not None else None,
                    "points": [
                        {"km": float(seg.start_km or 0), "pci": float(seg.pci_score) if seg.pci_score is not None else 100}
                        for seg in segs
                    ],
                })
            history_segments_json = json.dumps(history_lines)

    # Build display-friendly defect summary
    defect_summary_display = []
    if session.defect_summary:
        color_map = {
            "pothole": "#ef4444", "D40": "#ef4444", "D50": "#ef4444",
            "d40": "#ef4444", "d50": "#ef4444",
            "alligator_crack": "#f97316", "D20": "#f97316", "d20": "#f97316",
            "D00": "#3b82f6", "longitudinal_crack": "#3b82f6", "d00": "#3b82f6",
            "D10": "#8b5cf6", "transverse_crack": "#8b5cf6", "d10": "#8b5cf6",
        }
        for raw_type, count in session.defect_summary.items():
            defect_summary_display.append({
                "raw": raw_type,
                "name": get_defect_display_name(raw_type),
                "count": count,
                "color": color_map.get(raw_type, "#94a3b8"),
            })

    # Severity counts for filter chips
    sev_counts = {"critical": 0, "high": 0, "medium": 0}
    for d in detections:
        if d.severity in sev_counts:
            sev_counts[d.severity] += 1

    context = {
        "session": session,
        "detections": detections,
        "segments": segments,
        "filter_chips": filter_chips,
        "sev_counts": sev_counts,
        "defect_summary_display": defect_summary_display,
        "history_json": history_json,
        "history_segments_json": history_segments_json,
        "segments_json": json.dumps([
            {
                "index": s.segment_index,
                "start_km": float(s.start_km or 0),
                "end_km": float(s.end_km or 0),
                "pci": float(s.pci_score) if s.pci_score is not None else 100,
                "rating": s.condition_rating or "good",
                "color": s.color or "#22c55e",
                "defects": s.defect_count or 0,
                "track": s.track_points or [],
            }
            for s in segments
        ]),
        "detections_json": json.dumps(_build_detections_json(detections, _safe_thumb)),
    }
    return render(request, "sessions/session_detail.html", context)


@login_required
@require_POST
def session_upload(request):
    """Upload one or more session zips and process them."""
    zip_files = request.FILES.getlist("session_zip")
    if not zip_files:
        messages.error(request, _("No file uploaded."))
        return redirect("sessions:network_map")

    uploaded_ids = []
    error_count = 0

    for zip_file in zip_files:
        if not zip_file.name.lower().endswith(".zip"):
            messages.error(
                request,
                _("‘%(name)s’ is not a .zip archive — skipped.") % {"name": zip_file.name},
            )
            error_count += 1
            continue

        try:
            session = ingest_session(request.user, zip_file)
            messages.success(
                request,
                _(
                    "Session ‘%(session)s’ processed: %(defects)s defects, "
                    "%(segments)s segments, PCI %(pci)s"
                ) % {
                    "session": session.session_id,
                    "defects": session.total_defects,
                    "segments": session.total_segments,
                    "pci": session.avg_pci,
                }
            )
            uploaded_ids.append(str(session.pk))
        except IngestError as e:
            messages.error(
                request,
                _("Upload failed for ‘%(name)s’: %(error)s") % {"name": zip_file.name, "error": e},
            )
            error_count += 1

    # Always redirect to network map with uploaded session IDs for highlighting
    url = "/sessions/"
    if uploaded_ids:
        url += "?new=" + ",".join(uploaded_ids)
    return redirect(url)


@login_required
@require_POST
def session_delete(request, session_id):
    """Delete a session and all associated data."""
    session = get_object_or_404(Session, pk=session_id, user=request.user)
    sid = session.session_id

    # Delete files from disk
    import shutil
    if os.path.exists(session.data_dir):
        shutil.rmtree(session.data_dir, ignore_errors=True)

    session.delete()
    messages.success(request, _("Session ‘%(session)s’ deleted.") % {"session": sid})
    return redirect("sessions:network_map")


@login_required
@require_POST
def session_rename(request, session_id):
    """Rename a session (set road name) via AJAX. Also updates siblings with the same old road_name."""
    session = get_object_or_404(Session, pk=session_id, user=request.user)
    data = json.loads(request.body)
    new_name = data.get("road_name", "").strip()
    if new_name:
        old_name = session.road_name
        session.road_name = new_name
        session.save(update_fields=["road_name"])
        # Propagate rename to sibling sessions that share the old road_name
        if old_name:
            Session.objects.filter(
                user=request.user, road_name=old_name,
            ).update(road_name=new_name)
        return JsonResponse({"road_name": session.road_name, "display_name": session.display_name})
    return JsonResponse({"error": _("Name cannot be empty")}, status=400)


@login_required
@require_POST
def detection_verify(request, detection_id):
    """Verify or reject a detection (AJAX)."""
    detection = get_object_or_404(Detection, pk=detection_id, session__user=request.user)

    data = json.loads(request.body)
    status_str = data.get("status")

    if status_str == "verified":
        detection.verification_status = Detection.VerificationStatus.VERIFIED
    elif status_str == "rejected":
        detection.verification_status = Detection.VerificationStatus.REJECTED
    else:
        return JsonResponse({"error": _("Invalid status")}, status=400)

    detection.verified_by = request.user
    detection.verified_at = timezone.now()
    detection.verification_note = data.get("note", "")
    detection.save()

    # Update session verified count
    session = detection.session
    session.total_defects_verified = Detection.objects.filter(
        session=session, is_duplicate=False,
        verification_status=Detection.VerificationStatus.VERIFIED,
    ).count()
    session.save(update_fields=["total_defects_verified"])

    return JsonResponse({
        "status": status_str,
        "detection_id": detection_id,
    })


# ============================================================================
# JSON API endpoints for map data
# ============================================================================
@login_required
def api_session_geojson(request, session_id):
    """GeoJSON FeatureCollection of session segments for map rendering."""
    session = get_object_or_404(Session, pk=session_id, user=request.user)
    segments = RoadSegment.objects.filter(session=session).order_by("segment_index")

    features = []
    for seg in segments:
        if not seg.track_points or len(seg.track_points) < 2:
            continue
        coordinates = [[p[1], p[0]] for p in seg.track_points]  # [lon, lat]
        features.append({
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": coordinates},
            "properties": {
                "segment_index": seg.segment_index,
                "pci_score": seg.pci_score,
                "condition_rating": seg.condition_rating,
                "color": seg.color,
                "defect_count": seg.defect_count,
                "start_km": seg.start_km,
                "end_km": seg.end_km,
            },
        })

    return JsonResponse({"type": "FeatureCollection", "features": features})


@login_required
def api_detections_geojson(request, session_id):
    """GeoJSON points for detection markers on the map."""
    session = get_object_or_404(Session, pk=session_id, user=request.user)
    detections = Detection.objects.filter(
        session=session, is_duplicate=False,
    )

    features = []
    for det in detections:
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [det.lon, det.lat]},
            "properties": {
                "id": det.id,
                "defect_type": det.defect_type,
                "severity": det.severity,
                "confidence": round(det.confidence, 2),
                "distance_km": det.distance_km,
                "verification": det.verification_status_name,
            },
        })

    return JsonResponse({"type": "FeatureCollection", "features": features})


@login_required
def api_network_geojson(request):
    """All sessions as GeoJSON for network overview map."""
    sessions = Session.objects.filter(user=request.user, status=Session.Status.READY)

    features = []
    for session in sessions:
        for seg in session.segments.all():
            if not seg.track_points or len(seg.track_points) < 2:
                continue
            coordinates = [[p[1], p[0]] for p in seg.track_points]
            features.append({
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": coordinates},
                "properties": {
                    "session_id": session.pk,
                    "session_name": session.session_id,
                    "segment_index": seg.segment_index,
                    "pci_score": seg.pci_score,
                    "color": seg.color,
                    "condition_rating": seg.condition_rating,
                    "defect_count": seg.defect_count,
                    "date": session.start_time.isoformat() if session.start_time else None,
                },
            })

    return JsonResponse({"type": "FeatureCollection", "features": features})


@login_required
def api_network_stats(request):
    """Network-level statistics as JSON."""
    sessions = Session.objects.filter(user=request.user, status=Session.Status.READY)

    total_dist = sum(s.distance_km for s in sessions)
    total_defects = sum(s.total_defects for s in sessions)
    pcis = [s.avg_pci for s in sessions if s.avg_pci is not None]
    avg_pci = round(sum(pcis) / len(pcis), 1) if pcis else None

    by_type = {}
    for s in sessions:
        if s.defect_summary:
            for dtype, count in s.defect_summary.items():
                by_type[dtype] = by_type.get(dtype, 0) + count

    return JsonResponse({
        "total_sessions": sessions.count(),
        "total_distance_km": round(total_dist, 1),
        "total_defects": total_defects,
        "avg_pci": avg_pci,
        "defects_by_type": by_type,
    })
