from django.urls import path
from . import views

app_name = "projects"

urlpatterns = [
    path("", views.index, name="index"),
    path("summary/", views.projects_summary, name="summary"),
    path("<int:project_id>/upload/", views.upload, name="upload"),
    path("<int:project_id>/process/", views.process, name="process"),
    path("<int:project_id>/delete/", views.delete, name="delete"),
    path("<int:project_id>/status/", views.project_status, name="status"),
]
