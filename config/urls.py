"""Root URL routing — all REST endpoints live under /api/v1/ (§3)."""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include("apps.checks.urls")),
]
