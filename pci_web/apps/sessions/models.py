"""
Models for front-camera session-based road inspection.
Each session = one drive, containing GPS track, detections, and video.
"""
import os
from django.utils.translation import gettext_lazy as _
from django.db import models
from django.conf import settings
from django.contrib.auth.models import User


class Session(models.Model):
    """One inspection drive — historical snapshot for temporal comparison."""

    class Status(models.IntegerChoices):
        UPLOADING = 0, _("Uploading")
        PROCESSING = 1, _("Processing")
        READY = 2, _("Ready")
        ERROR = 3, _("Error")

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="sessions")
    session_id = models.CharField(max_length=64, unique=True, db_index=True)
    city = models.CharField(max_length=128, blank=True, default="")
    road_name = models.CharField(max_length=255, blank=True, default="")
    status = models.IntegerField(choices=Status.choices, default=Status.UPLOADING)
    processing_error = models.TextField(blank=True, default="")

    # Temporal
    start_time = models.DateTimeField(null=True, blank=True)
    end_time = models.DateTimeField(null=True, blank=True)

    # Distance
    distance_km = models.FloatField(default=0.0)

    # Device info
    device = models.CharField(max_length=128, blank=True, default="")
    camera = models.CharField(max_length=128, blank=True, default="")
    camera_type = models.CharField(max_length=16, default="front")
    model_name = models.CharField(max_length=128, blank=True, default="")
    confidence_threshold = models.FloatField(null=True, blank=True)

    # Aggregated results
    avg_pci = models.FloatField(null=True, blank=True, db_index=True)
    condition_rating = models.CharField(max_length=32, blank=True, default="")
    total_defects = models.IntegerField(default=0)
    total_defects_verified = models.IntegerField(default=0)
    total_segments = models.IntegerField(default=0)
    defect_summary = models.JSONField(null=True, blank=True)

    # Full metadata from Jetson
    session_metadata = models.JSONField(null=True, blank=True)

    # Bounding box for spatial queries
    min_lat = models.FloatField(null=True, blank=True)
    max_lat = models.FloatField(null=True, blank=True)
    min_lon = models.FloatField(null=True, blank=True)
    max_lon = models.FloatField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["user", "-created_at"]),
        ]

    def __str__(self):
        return self.display_name

    @property
    def display_name(self):
        if self.road_name:
            return self.road_name
        return self.session_id

    @property
    def is_ready(self):
        return self.status == self.Status.READY

    @property
    def duration_minutes(self):
        if self.start_time and self.end_time:
            return round((self.end_time - self.start_time).total_seconds() / 60, 1)
        return None

    @property
    def data_dir(self):
        return os.path.join(settings.MEDIA_ROOT, "sessions", self.session_id)

    @property
    def video_path(self):
        d = self.data_dir
        for ext in (".mp4", ".h265", ".hevc"):
            p = os.path.join(d, f"video{ext}")
            if os.path.exists(p):
                return p
        return None

    @property
    def video_url(self):
        vp = self.video_path
        if vp:
            rel = os.path.relpath(vp, settings.MEDIA_ROOT)
            return f"{settings.MEDIA_URL}{rel}"
        return None


class RoadSegment(models.Model):
    """100m road segment with PCI score — powers the color-coded map."""

    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name="segments")
    segment_index = models.IntegerField()

    # Distance range
    start_km = models.FloatField()
    end_km = models.FloatField()

    # GPS boundaries
    start_lat = models.FloatField()
    start_lon = models.FloatField()
    end_lat = models.FloatField()
    end_lon = models.FloatField()

    # Track points for polyline [[lat, lon], ...]
    track_points = models.JSONField(null=True, blank=True)

    # PCI
    pci_score = models.FloatField(default=100.0, db_index=True)
    condition_rating = models.CharField(max_length=32, default="good")
    color = models.CharField(max_length=10, default="#16a34a")

    # Defect stats
    defect_count = models.IntegerField(default=0)
    defect_breakdown = models.JSONField(null=True, blank=True)
    deductions = models.JSONField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["segment_index"]
        unique_together = ["session", "segment_index"]

    def __str__(self):
        return f"Seg {self.segment_index} PCI={self.pci_score}"


class Detection(models.Model):
    """Individual defect detection with human verification."""

    class VerificationStatus(models.IntegerChoices):
        PENDING = 0, _("Pending")
        VERIFIED = 1, _("Verified")
        REJECTED = 2, _("Rejected")

    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name="detections")
    segment = models.ForeignKey(
        RoadSegment, on_delete=models.SET_NULL, null=True, blank=True, related_name="detections",
    )

    detection_seq = models.IntegerField()
    defect_type = models.CharField(max_length=64, db_index=True)
    confidence = models.FloatField()
    severity = models.CharField(max_length=16, db_index=True)
    priority = models.IntegerField(default=3)

    # GPS (last-frame method)
    lat = models.FloatField()
    lon = models.FloatField()
    speed = models.FloatField(null=True, blank=True)
    heading = models.FloatField(null=True, blank=True)

    # Video reference
    frame_number = models.IntegerField()
    timestamp = models.DateTimeField()
    distance_km = models.FloatField()
    bbox = models.JSONField(null=True, blank=True)

    # Thumbnail
    thumbnail = models.ImageField(upload_to="sessions/thumbnails/", null=True, blank=True)
    thumbnail_crop = models.ImageField(upload_to="sessions/thumbnails/", null=True, blank=True)

    # Verification
    verification_status = models.IntegerField(
        choices=VerificationStatus.choices, default=VerificationStatus.PENDING,
    )
    verified_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="verified_detections",
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    verification_note = models.TextField(blank=True, default="")

    is_duplicate = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["distance_km"]
        indexes = [
            models.Index(fields=["session", "defect_type"]),
            models.Index(fields=["session", "distance_km"]),
            models.Index(fields=["verification_status"]),
        ]

    def __str__(self):
        return f"{self.defect_type} ({self.confidence:.0%}) @ {self.distance_km:.2f}km"

    @property
    def verification_status_name(self):
        return self.VerificationStatus(self.verification_status).name.lower()

    DEFECT_DISPLAY_NAMES = {
        "D00": _("Longitudinal crack"),
        "D10": _("Transverse crack"),
        "D20": _("Alligator crack"),
        "D40": _("Pothole"),
        "D50": _("Pothole"),
        "d00": _("Longitudinal crack"),
        "d10": _("Transverse crack"),
        "d20": _("Alligator crack"),
        "d40": _("Pothole"),
        "d50": _("Pothole"),
        "pothole": _("Pothole"),
        "alligator_crack": _("Alligator crack"),
        "longitudinal_crack": _("Longitudinal crack"),
        "transverse_crack": _("Transverse crack"),
        "patch": _("Patch/repair"),
        "rutting": _("Rutting"),
        "bleeding": _("Bleeding"),
    }

    @property
    def defect_display_name(self):
        raw = (self.defect_type or "").strip()
        return (
            self.DEFECT_DISPLAY_NAMES.get(raw)
            or self.DEFECT_DISPLAY_NAMES.get(raw.lower())
            or self.DEFECT_DISPLAY_NAMES.get(raw.upper())
            or raw.replace("_", " ").title()
        )


class SessionFile(models.Model):
    """Raw files stored on disk (video, GPS track, detections, archive)."""

    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name="files")
    file_type = models.CharField(max_length=32)  # video, gps_track, detections_raw, metadata, archive
    file_path = models.CharField(max_length=500)
    original_filename = models.CharField(max_length=255, blank=True, default="")
    size_bytes = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.file_type}: {self.original_filename}"
