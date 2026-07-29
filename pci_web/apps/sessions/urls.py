from django.urls import path
from . import views
from .pdf_report import session_pdf_report, multi_session_pdf_report

app_name = "sessions"

urlpatterns = [
    # City selector and network map
    path("", views.city_selector, name="city_selector"),
    path("map/", views.network_map, name="network_map"),
    path("list/", views.session_list, name="list"),

    # Session views
    path("review/", views.multi_session_review, name="multi_review"),
    path("review/report.pdf", multi_session_pdf_report, name="multi_pdf_report"),
    path("<int:session_id>/", views.session_detail, name="detail"),
    path("<int:session_id>/report.pdf", session_pdf_report, name="pdf_report"),
    path("upload/", views.session_upload, name="upload"),
    path("<int:session_id>/delete/", views.session_delete, name="delete"),
    path("<int:session_id>/rename/", views.session_rename, name="rename"),

    # AJAX endpoints
    path("detection/<int:detection_id>/verify/", views.detection_verify, name="verify"),

    # JSON API for maps
    path("<int:session_id>/geojson/", views.api_session_geojson, name="geojson"),
    path("<int:session_id>/detections.json", views.api_detections_geojson, name="detections_json"),
    path("api/network/geojson/", views.api_network_geojson, name="network_geojson"),
    path("api/network/stats/", views.api_network_stats, name="network_stats"),
]
