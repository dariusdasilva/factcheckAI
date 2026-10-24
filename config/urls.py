"""Root URL routing — all REST endpoints live under /api/v1/ (§3)."""

from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include("apps.checks.urls")),
    path("api/v1/", include("apps.accounts.urls")),
]

# Serve the static web SPA from the repo root in development only, so the
# frontend runs same-origin against the API with no build step or CORS setup.
if settings.DEBUG:
    from pathlib import Path

    frontend = Path(settings.BASE_DIR) / "frontend" / "web"
    urlpatterns += [
        re_path(r"^(?P<path>api\.js|app\.js|style\.css)$", serve, {"document_root": frontend}),
        re_path(r"^$", serve, {"document_root": frontend, "path": "index.html"}),
    ]
