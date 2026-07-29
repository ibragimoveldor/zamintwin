from django.urls import path
from . import views

app_name = "projects"

urlpatterns = [
    path("", views.index, name="index"),
    path("<int:project_id>/upload/", views.upload, name="upload"),
    path("<int:project_id>/process/", views.process, name="process"),
    path("<int:project_id>/delete/", views.delete, name="delete"),
]
