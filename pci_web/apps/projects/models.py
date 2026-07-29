import os
from django.db import models
from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError


def validate_image_extension(value):
    ext = os.path.splitext(value.name)[-1].lower()
    valid_extensions = [".jpg", ".jpeg", ".png"]
    if ext not in valid_extensions:
        raise ValidationError(f"Unsupported file type: {ext}. Use JPG or PNG.")


import os
from django.core.files.storage import default_storage

def project_image_path(instance, filename):
    folder_name = instance.project.slug
    path = f"{folder_name}/images/{filename}"
    # Delete existing file to prevent Django adding random suffix
    if default_storage.exists(path):
        default_storage.delete(path)
    return path

class Project(models.Model):
    class Status(models.IntegerChoices):
        CREATED = 0, "Created"
        UPLOADED = 1, "Images Uploaded"
        PROCESSING = 2, "Processing"
        FAILED = 3, "Failed"
        COMPLETED = 4, "Completed"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="projects")
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, blank=True)
    lat = models.CharField(max_length=50, default="")
    lng = models.CharField(max_length=50, default="")
    status = models.IntegerField(choices=Status.choices, default=Status.CREATED)
    celery_task_id = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = ["user", "name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self.name.lower().replace(" ", "_")
        super().save(*args, **kwargs)

    @property
    def images_dir(self):
        return os.path.join(settings.MEDIA_ROOT, self.slug, "images")

    @property
    def results_dir(self):
        return os.path.join(settings.MEDIA_ROOT, self.slug, "result")

    @property
    def pci_dir(self):
        return os.path.join(settings.MEDIA_ROOT, self.slug, "pci")

    @property
    def image_count(self):
        return self.images.count()


class ProjectImage(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(
        upload_to=project_image_path,
        validators=[validate_image_extension],
        max_length=500,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return os.path.basename(self.image.name)
