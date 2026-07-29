from django.contrib import admin
from .models import PCIResult


@admin.register(PCIResult)
class PCIResultAdmin(admin.ModelAdmin):
    list_display = ["image_name", "project", "pci_rating", "pavement_condition"]
    list_filter = ["pavement_condition", "project"]
    search_fields = ["image_name"]
