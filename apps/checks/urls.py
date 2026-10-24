"""URLs for the checks API (A3 contract)."""

from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.checks import views

router = DefaultRouter()
router.register(r"checks", views.ChecksViewSet, basename="checks")

urlpatterns = router.urls + [
    path("health/", views.health, name="health"),
    path("spend/", views.spend_stub, name="spend"),
    path("models/", views.model_catalog_stub, name="models"),
    path("sources/", views.store_source, name="sources"),
]
