"""Schemas for the checks API (Chunk A3 builds the endpoints on these paths)."""

from django.urls import path

from apps.checks import views

app_name = "checks"

urlpatterns = [
    path("health/", views.health, name="health"),
]
