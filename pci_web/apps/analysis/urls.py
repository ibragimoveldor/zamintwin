from django.urls import path
from . import views

app_name = "analysis"

urlpatterns = [
    path("", views.index_view, name="index"),
    path("<int:project_id>/results/", views.results_view, name="results"),
    path("<int:project_id>/map/", views.map_view, name="map"),
    path("<int:project_id>/mapview/", views.map_view, name="mapview"),
    path("<int:project_id>/download/", views.download_csv, name="download"),
    path("<int:project_id>/export-pdf/", views.export_pdf, name="export_pdf"),
]
