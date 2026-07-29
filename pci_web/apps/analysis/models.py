from django.db import models
from apps.projects.models import Project


class PCIResult(models.Model):
    """
    Stores PCI results per image. Loaded from CSV ONCE after pipeline completes,
    not on every page view like the old code did.
    """
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="pci_results")
    image_name = models.CharField(max_length=255)
    pci_rating = models.FloatField(default=0)
    crack_length = models.FloatField(default=0)
    alligator_area = models.FloatField(default=0)
    patching_area = models.FloatField(default=0)
    pothole_area = models.FloatField(default=0)
    pavement_condition = models.CharField(max_length=50, default="Not Damaged")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["image_name"]
        unique_together = ["project", "image_name"]

    def __str__(self):
        return f"{self.image_name} - PCI: {self.pci_rating}"
