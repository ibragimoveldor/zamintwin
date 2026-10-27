from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("admin/", admin.site.urls),
    path("i18n/", include("django.conf.urls.i18n")),
    path("", include("apps.projects.urls")),
    path("accounts/", include("apps.accounts.urls")),
    path("analysis/", include("apps.analysis.urls")),
    path("reports/", include("apps.reports.urls")),
    path("sessions/", include("apps.sessions.urls")),    # ← add this line

    # API endpoints (versioned)
    path("api/v1/", include("apps.api_urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=str(settings.BASE_DIR / "static"))

