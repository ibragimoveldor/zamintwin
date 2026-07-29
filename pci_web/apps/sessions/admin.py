from django.contrib import admin
from .models import Session, Detection, RoadSegment, SessionFile


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = ["session_id", "user", "status", "avg_pci", "total_defects", "distance_km", "created_at"]
    list_filter = ["status", "condition_rating"]
    search_fields = ["session_id"]


@admin.register(Detection)
class DetectionAdmin(admin.ModelAdmin):
    list_display = ["defect_type", "confidence", "severity", "verification_status", "distance_km"]
    list_filter = ["defect_type", "severity", "verification_status", "is_duplicate"]


@admin.register(RoadSegment)
class RoadSegmentAdmin(admin.ModelAdmin):
    list_display = ["session", "segment_index", "pci_score", "condition_rating", "defect_count"]
    list_filter = ["condition_rating"]


@admin.register(SessionFile)
class SessionFileAdmin(admin.ModelAdmin):
    list_display = ["session", "file_type", "original_filename", "size_bytes"]
