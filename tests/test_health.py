"""A1 deliverable: health endpoint acceptance tests (WORK_CHUNKS.md Chunk A).

Contract (ARCHITECTURE.md §3): GET /api/v1/health/ is public, returns 200 JSON
with the DB state, and lets clients pre-emptively show a "degraded" banner.
"""

import pytest
from rest_framework.test import APIClient

pytestmark = [pytest.mark.django_db]


def test_health_returns_200_json_with_db_ok():
    client = APIClient()
    response = client.get("/api/v1/health/")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["components"]["database"] == "ok"
    assert body["components"]["queue"] == "ok"  # django_q configured since A4


def test_health_queue_component_reports_unconfigured(monkeypatch):
    from django.conf import settings
    from django.test import Client

    monkeypatch.setattr(
        settings, "INSTALLED_APPS", [a for a in settings.INSTALLED_APPS if a != "django_q"]
    )
    response = Client().get("/api/v1/health/")
    assert response.json()["components"]["queue"] == "not_configured"
