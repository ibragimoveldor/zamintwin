"""
Session ingest pipeline for Django.
Extracts zip → validates → stores files → parses → deduplicates → scores PCI.
"""
import io
import json
import math
import os
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings

from .models import Session, Detection, RoadSegment, SessionFile


SEGMENT_LENGTH_KM = 0.1  # 100 meters
DEDUP_RADIUS_KM = 0.010  # 10 meters
OVERLAP_RADIUS_KM = 0.050  # 50 meters — threshold for "same road"
OVERLAP_MIN_RATIO = 0.30  # 30% of sampled points must be near existing track
REQUIRED_FILES = {"metadata.json", "detections.jsonl", "gps_track.jsonl"}

# PCI deduction weights
DEDUCTION_WEIGHTS = {
    "pothole":             {"critical": 15.0, "high": 8.0, "medium": 4.0},
    "Pothole":             {"critical": 15.0, "high": 8.0, "medium": 4.0},
    "D40":                 {"critical": 15.0, "high": 8.0, "medium": 4.0},
    "D50":                 {"critical": 15.0, "high": 8.0, "medium": 4.0},
    "alligator_crack":     {"critical": 10.0, "high": 6.0, "medium": 3.0},
    "Alligator Crack":     {"critical": 10.0, "high": 6.0, "medium": 3.0},
    "D20":                 {"critical": 10.0, "high": 6.0, "medium": 3.0},
    "longitudinal_crack":  {"critical": 7.0,  "high": 5.0, "medium": 2.0},
    "Longitudinal Crack":  {"critical": 7.0,  "high": 5.0, "medium": 2.0},
    "D00":                 {"critical": 7.0,  "high": 5.0, "medium": 2.0},
    "transverse_crack":    {"critical": 6.0,  "high": 4.0, "medium": 2.0},
    "Transverse Crack":    {"critical": 6.0,  "high": 4.0, "medium": 2.0},
    "D10":                 {"critical": 6.0,  "high": 4.0, "medium": 2.0},
}
DEFAULT_DEDUCTIONS = {"critical": 5.0, "high": 3.0, "medium": 1.5}

PCI_RATINGS = [
    (85, "good", "#16a34a"),
    (70, "satisfactory", "#84cc16"),
    (55, "fair", "#eab308"),
    (40, "poor", "#ea580c"),
    (25, "very_poor", "#dc2626"),
    (0,  "failed", "#7f1d1d"),
]


def get_rating_and_color(pci):
    for threshold, rating, color in PCI_RATINGS:
        if pci >= threshold:
            return rating, color
    return "failed", "#7f1d1d"


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def parse_dt(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


class IngestError(Exception):
    pass


def _get_road_and_city_from_gps(gps_points):
    """
    Reverse-geocode the midpoint of a GPS track using OpenStreetMap Nominatim.
    Returns (road_name, city) tuple. Both default to "" on failure.
    """
    if not gps_points:
        return "", ""
    mid = gps_points[len(gps_points) // 2]
    lat, lon = mid["lat"], mid["lon"]
    url = (
        f"https://nominatim.openstreetmap.org/reverse"
        f"?lat={lat}&lon={lon}&format=json&zoom=17"
    )
    try:
        try:
            import requests as _requests
            resp = _requests.get(
                url,
                headers={"User-Agent": "ZaminTwin/1.0"},
                timeout=5,
            )
            data = resp.json()
        except ImportError:
            from urllib.request import Request, urlopen
            req = Request(url, headers={"User-Agent": "ZaminTwin/1.0"})
            with urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        address = data.get("address", {})
        road = address.get("road", "") or data.get("display_name", "")
        city = (address.get("city", "")
                or address.get("town", "")
                or address.get("county", "")
                or address.get("state", ""))
        return road, city
    except Exception:
        return "", ""


def _find_overlapping_road(user, gps_points, exclude_session=None):
    """
    Check if the GPS track of a new session overlaps with any existing session.
    Returns the road_name of the best-matching session, or "" if no overlap.

    Algorithm:
    - Sample up to 20 evenly spaced points from the new track
    - For each existing READY session with a bounding-box overlap,
      check how many sampled points fall within OVERLAP_RADIUS_KM of
      any point on the existing track
    - If >= OVERLAP_MIN_RATIO of sampled points match, it's the same road
    """
    if len(gps_points) < 2:
        return ""

    # Sample evenly spaced points from new track
    step = max(1, len(gps_points) // 20)
    samples = gps_points[::step]

    new_min_lat = min(p["lat"] for p in gps_points) - 0.001
    new_max_lat = max(p["lat"] for p in gps_points) + 0.001
    new_min_lon = min(p["lon"] for p in gps_points) - 0.001
    new_max_lon = max(p["lon"] for p in gps_points) + 0.001

    # Find candidate sessions with overlapping bounding boxes
    candidates = Session.objects.filter(
        user=user,
        status=Session.Status.READY,
        min_lat__isnull=False,
    ).exclude(
        min_lat__gt=new_max_lat,
    ).exclude(
        max_lat__lt=new_min_lat,
    ).exclude(
        min_lon__gt=new_max_lon,
    ).exclude(
        max_lon__lt=new_min_lon,
    )

    if exclude_session:
        candidates = candidates.exclude(pk=exclude_session.pk)

    best_match_name = ""
    best_match_session = None
    best_ratio = 0.0

    for candidate in candidates:
        # Load the candidate's GPS track points from its segments
        seg_points = []
        for seg in candidate.segments.all():
            if seg.track_points:
                for pt in seg.track_points:
                    seg_points.append((pt[0], pt[1]))  # (lat, lon)

        if not seg_points:
            continue

        # Count how many of our sampled points are near the candidate track
        near_count = 0
        for sp in samples:
            for cp_lat, cp_lon in seg_points:
                if haversine_km(sp["lat"], sp["lon"], cp_lat, cp_lon) <= OVERLAP_RADIUS_KM:
                    near_count += 1
                    break

        ratio = near_count / len(samples)
        if ratio >= OVERLAP_MIN_RATIO and ratio > best_ratio:
            best_ratio = ratio
            best_match_name = candidate.road_name or candidate.display_name
            best_match_session = candidate

    # If the matched session didn't have a road_name, set it now so both share the same name
    if best_match_session and not best_match_session.road_name and best_match_name:
        best_match_session.road_name = best_match_name
        best_match_session.save(update_fields=["road_name"])

    return best_match_name


def ingest_session(user, zip_file):
    """
    Main ingest pipeline. Takes a Django UploadedFile (zip),
    returns a Session object.
    """
    session = None
    try:
        # --- Step 1: Extract and validate ---
        try:
            zf = zipfile.ZipFile(io.BytesIO(zip_file.read()))
        except zipfile.BadZipFile:
            raise IngestError("Invalid zip file")

        file_map = {}
        video_name = None
        thumbnail_files = {}  # det_id -> zip_path
        for name in zf.namelist():
            basename = Path(name).name
            if basename in REQUIRED_FILES:
                file_map[basename] = name
            if basename.lower().endswith((".mp4", ".h265", ".hevc")):
                video_name = name
            # Collect pre-extracted thumbnails (thumbnails/det_1.jpg, etc.)
            if "thumbnails/" in name and basename.lower().endswith(".jpg"):
                thumbnail_files[basename] = name

        missing = REQUIRED_FILES - set(file_map.keys())
        if missing:
            raise IngestError(f"Missing required files: {', '.join(missing)}")

        files = {key: zf.read(path) for key, path in file_map.items()}
        if video_name:
            files["video"] = zf.read(video_name)
            files["_video_filename"] = Path(video_name).name

        # --- Step 2: Parse metadata ---
        metadata = json.loads(files["metadata.json"])
        sid = metadata["session_id"]

        if Session.objects.filter(session_id=sid).exists():
            raise IngestError(f"Session '{sid}' already exists")

        # --- Step 3: Create session ---
        session = Session.objects.create(
            user=user,
            session_id=sid,
            status=Session.Status.PROCESSING,
            start_time=parse_dt(metadata.get("start_time")),
            end_time=parse_dt(metadata.get("end_time")),
            distance_km=metadata.get("total_distance_km", 0.0),
            device=metadata.get("device", ""),
            camera=metadata.get("camera", ""),
            camera_type=metadata.get("camera_type", "front"),
            model_name=metadata.get("model", ""),
            confidence_threshold=metadata.get("confidence_threshold"),
            total_defects=metadata.get("total_defects", 0),
            defect_summary=metadata.get("defect_summary"),
            session_metadata=metadata,
        )

        # --- Step 4: Store raw files to disk ---
        data_dir = session.data_dir
        os.makedirs(data_dir, exist_ok=True)

        for fname, data in [
            ("metadata.json", files["metadata.json"]),
            ("detections.jsonl", files["detections.jsonl"]),
            ("gps_track.jsonl", files["gps_track.jsonl"]),
        ]:
            fpath = os.path.join(data_dir, fname)
            with open(fpath, "wb") as f:
                f.write(data)
            SessionFile.objects.create(
                session=session, file_type=fname.split(".")[0],
                file_path=fpath, original_filename=fname, size_bytes=len(data),
            )

        if "video" in files:
            vname = files.get("_video_filename", "video.mp4")
            vpath = os.path.join(data_dir, vname)
            with open(vpath, "wb") as f:
                f.write(files["video"])
            SessionFile.objects.create(
                session=session, file_type="video",
                file_path=vpath, original_filename=vname, size_bytes=len(files["video"]),
            )

        # Save pre-extracted thumbnails from zip (if any)
        if thumbnail_files:
            thumb_dir = os.path.join(data_dir, "thumbnails")
            os.makedirs(thumb_dir, exist_ok=True)
            for basename, zip_path in thumbnail_files.items():
                thumb_data = zf.read(zip_path)
                thumb_fpath = os.path.join(thumb_dir, basename)
                with open(thumb_fpath, "wb") as f:
                    f.write(thumb_data)

        # Save archive
        zip_file.seek(0)
        archive_path = os.path.join(data_dir, "archive.zip")
        with open(archive_path, "wb") as f:
            shutil.copyfileobj(zip_file, f)

        # --- Step 5: Parse GPS track ---
        gps_points = []
        for line in files["gps_track.jsonl"].decode("utf-8").strip().split("\n"):
            if not line.strip():
                continue
            try:
                p = json.loads(line)
                if "lat" in p and "lon" in p:
                    gps_points.append(p)
            except json.JSONDecodeError:
                continue

        if gps_points:
            lats = [p["lat"] for p in gps_points]
            lons = [p["lon"] for p in gps_points]
            session.min_lat = min(lats)
            session.max_lat = max(lats)
            session.min_lon = min(lons)
            session.max_lon = max(lons)

        # --- Step 5b: Auto-detect road overlap ---
        if gps_points and not session.road_name:
            matched_road = _find_overlapping_road(user, gps_points, exclude_session=session)
            if matched_road:
                session.road_name = matched_road
                session.save(update_fields=["road_name", "min_lat", "max_lat", "min_lon", "max_lon"])

        # --- Step 5c: Auto-name and city from GPS ---
        if gps_points and not session.road_name:
            name, city = _get_road_and_city_from_gps(gps_points)
            if name:
                session.road_name = name
            if city and not session.city:
                session.city = city

        # --- Step 6: Parse detections ---
        raw_detections = []
        for line in files["detections.jsonl"].decode("utf-8").strip().split("\n"):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                if "event" in record:
                    continue
                if "id" in record and "type" in record:
                    raw_detections.append(record)
            except json.JSONDecodeError:
                continue

        det_objects = []
        for det in raw_detections:
            d = Detection(
                session=session,
                detection_seq=det["id"],
                defect_type=det["type"],
                confidence=det["confidence"],
                severity=det["severity"],
                priority=det.get("priority", 3),
                lat=det["gps"]["lat"],
                lon=det["gps"]["lon"],
                speed=det["gps"].get("speed"),
                heading=det["gps"].get("heading"),
                frame_number=det["frame"],
                timestamp=parse_dt(det["timestamp"]),
                distance_km=det["distance_km"],
                bbox=det.get("bbox"),
            )
            det_objects.append(d)

        Detection.objects.bulk_create(det_objects)
        # Refresh to get IDs
        det_objects = list(
            Detection.objects.filter(session=session).order_by("distance_km")
        )

        # --- Step 7: Deduplicate ---
        _deduplicate(det_objects)

        # --- Step 8: Build 100m segments ---
        max_dist = session.distance_km or (
            gps_points[-1].get("dist_km", 0) if gps_points else 0
        )
        num_segments = max(1, math.ceil(max_dist / SEGMENT_LENGTH_KM))

        segments = []
        for idx in range(num_segments):
            start_km = round(idx * SEGMENT_LENGTH_KM, 3)
            end_km = round((idx + 1) * SEGMENT_LENGTH_KM, 3)

            # Include points in [start_km, end_km) range
            seg_gps = [p for p in gps_points if start_km <= p.get("dist_km", 0) < end_km]

            # Overlap: grab the first point of the NEXT segment so lines connect
            next_start = [p for p in gps_points if p.get("dist_km", 0) >= end_km]
            if next_start:
                seg_gps.append(next_start[0])

            if not seg_gps and gps_points:
                mid = (start_km + end_km) / 2
                seg_gps = [min(gps_points, key=lambda p: abs(p.get("dist_km", 0) - mid))]

            track_coords = [[p["lat"], p["lon"]] for p in seg_gps]
            sp = seg_gps[0] if seg_gps else gps_points[0]
            ep = seg_gps[-1] if seg_gps else gps_points[-1]

            segments.append(RoadSegment(
                session=session, segment_index=idx,
                start_km=start_km, end_km=end_km,
                start_lat=sp["lat"], start_lon=sp["lon"],
                end_lat=ep["lat"], end_lon=ep["lon"],
                track_points=track_coords,
            ))

        RoadSegment.objects.bulk_create(segments)
        segments = list(
            RoadSegment.objects.filter(session=session).order_by("segment_index")
        )

        # --- Step 9: Assign detections to segments ---
        active_dets = [d for d in det_objects if not d.is_duplicate]
        for det in active_dets:
            for seg in segments:
                if seg.start_km <= det.distance_km < seg.end_km:
                    det.segment = seg
                    det.save(update_fields=["segment"])
                    break

        # --- Step 10: Score PCI per segment ---
        # --- Step 9.5: Extract thumbnails from video (if available) ---
        _extract_thumbnails(session, active_dets)

        # --- Step 10: Score PCI per segment ---
        segment_scores = []
        for seg in segments:
            seg_dets = [
                d for d in active_dets
                if seg.start_km <= d.distance_km < seg.end_km
            ]
            pci, rating, color, breakdown, ded_log = _score_segment(seg_dets)
            seg.pci_score = pci
            seg.condition_rating = rating
            seg.color = color
            seg.defect_count = len(seg_dets)
            seg.defect_breakdown = breakdown
            seg.deductions = ded_log
            seg.save()
            segment_scores.append(pci)

        # --- Step 11: Update session ---
        avg_pci = round(sum(segment_scores) / len(segment_scores), 1) if segment_scores else 100.0
        avg_rating, _ = get_rating_and_color(avg_pci)

        summary = {}
        for d in active_dets:
            summary[d.defect_type] = summary.get(d.defect_type, 0) + 1

        session.avg_pci = avg_pci
        session.condition_rating = avg_rating
        session.total_defects = len(active_dets)
        session.total_segments = len(segments)
        session.defect_summary = summary
        session.status = Session.Status.READY
        session.save()

        return session

    except IngestError:
        if session:
            session.status = Session.Status.ERROR
            session.processing_error = str("Validation error")
            session.save()
        raise
    except Exception as e:
        if session:
            session.status = Session.Status.ERROR
            session.processing_error = str(e)[:500]
            session.save()
        raise IngestError(f"Ingest failed: {e}") from e


def _deduplicate(det_objects):
    """Mark duplicate detections within 10m GPS radius (same class)."""
    by_type = {}
    for d in det_objects:
        by_type.setdefault(d.defect_type, []).append(d)

    to_update = []
    for dtype, dets in by_type.items():
        dets.sort(key=lambda d: d.distance_km)
        i = 0
        while i < len(dets):
            if dets[i].is_duplicate:
                i += 1
                continue
            cluster = [dets[i]]
            j = i + 1
            while j < len(dets):
                if dets[j].is_duplicate:
                    j += 1
                    continue
                dist = haversine_km(dets[i].lat, dets[i].lon, dets[j].lat, dets[j].lon)
                if dist <= DEDUP_RADIUS_KM:
                    cluster.append(dets[j])
                    j += 1
                else:
                    break
            if len(cluster) > 1:
                best = max(cluster, key=lambda d: d.confidence)
                last = max(cluster, key=lambda d: d.frame_number)
                best.lat = last.lat
                best.lon = last.lon
                best.distance_km = last.distance_km
                best.save(update_fields=["lat", "lon", "distance_km"])
                for d in cluster:
                    if d is not best:
                        d.is_duplicate = True
                        to_update.append(d)
            i = j

    if to_update:
        Detection.objects.bulk_update(to_update, ["is_duplicate"])


def _score_segment(detections):
    """Calculate PCI for a segment. Returns (pci, rating, color, breakdown, deductions)."""
    breakdown = {}
    ded_items = []
    for d in detections:
        weights = DEDUCTION_WEIGHTS.get(d.defect_type, DEFAULT_DEDUCTIONS)
        ded = weights.get(d.severity, 2.0)
        ded_items.append({"type": d.defect_type, "severity": d.severity, "deduction": ded})
        breakdown.setdefault(d.defect_type, {})
        breakdown[d.defect_type][d.severity] = breakdown[d.defect_type].get(d.severity, 0) + 1

    total_ded = min(sum(d["deduction"] for d in ded_items), 100)
    pci = round(max(0, 100 - total_ded), 1)
    rating, color = get_rating_and_color(pci)

    return pci, rating, color, breakdown, {"items": ded_items, "total": total_ded}


def _extract_thumbnails(session, detections):
    """
    Assign thumbnails to detections.
    1. Check for pre-extracted thumbnails (from zip's thumbnails/ folder).
    2. Fall back to extracting from video with ffmpeg.
    """
    import subprocess
    import shutil
    from django.conf import settings

    thumb_dir = os.path.join(session.data_dir, "thumbnails")
    os.makedirs(thumb_dir, exist_ok=True)

    # Step 1: Check for pre-extracted thumbnails (det_{seq_id}.jpg)
    pre_extracted_count = 0
    for det in detections:
        if det.is_duplicate:
            continue
        pre_path = os.path.join(thumb_dir, f"det_{det.detection_seq}.jpg")
        if os.path.exists(pre_path) and os.path.getsize(pre_path) > 0:
            # Copy to det_{pk}.jpg
            dst = os.path.join(thumb_dir, f"det_{det.pk}.jpg")
            if pre_path != dst:
                shutil.copy2(pre_path, dst)
            rel_path = os.path.relpath(dst, settings.MEDIA_ROOT)
            det.thumbnail = rel_path
            det.save(update_fields=["thumbnail"])
            pre_extracted_count += 1

    if pre_extracted_count > 0:
        return  # Pre-extracted thumbnails found, no need for ffmpeg

    # Step 2: Fall back to video extraction
    if not shutil.which("ffmpeg"):
        return

    video_file = None
    for sf in session.files.filter(file_type="video"):
        if os.path.exists(sf.file_path):
            video_file = sf.file_path
            break

    if not video_file:
        return

    for det in detections:
        if det.is_duplicate or not det.timestamp or not session.start_time:
            continue

        try:
            offset = (det.timestamp - session.start_time).total_seconds()
            if offset < 0:
                offset = 0

            thumb_path = os.path.join(thumb_dir, f"det_{det.pk}.jpg")
            cmd = [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-i", video_file,
                "-ss", f"{offset:.2f}",
                "-vframes", "1",
                "-q:v", "3",
                "-vf", "scale=640:-1",
                thumb_path,
            ]
            subprocess.run(cmd, timeout=30, capture_output=True)

            if os.path.exists(thumb_path) and os.path.getsize(thumb_path) > 0:
                rel_path = os.path.relpath(thumb_path, settings.MEDIA_ROOT)
                det.thumbnail = rel_path
                det.save(update_fields=["thumbnail"])

        except Exception:
            continue
