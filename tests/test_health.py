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
