"""A4 deliverable: throttling acceptance — request #101 is blocked with 429.

Rate: 100 requests/day per user (ARCHITECTURE.md §3), applied globally, with
the health probe exempt. Cache is cleared per test since LocMem persists
across a test session and would otherwise leak throttle history between tests.
"""

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

pytestmark = [pytest.mark.django_db]


def _fresh_throttled_client(django_user_model, username: str):
    """Fresh user + client: per-user throttle keys start at zero requests."""
    cache.clear()
    user = django_user_model.objects.create_user(username=username, password="x")
    client = APIClient()
    client.force_authenticate(user=user)
    return client, user


@pytest.fixture()
def client_fixture(django_user_model):
    return _fresh_throttled_client(django_user_model, "ratelimited")


def test_throttle_blocks_request_101(client_fixture):
    client, _ = client_fixture
    for _ in range(100):
        response = client.get("/api/v1/checks/")
        assert response.status_code == 200

    blocked = client.get("/api/v1/checks/")
    assert blocked.status_code == 429


def test_throttle_is_per_user_and_blocks_other_endpoints_too(client_fixture, django_user_model):
    client, _ = client_fixture
    for _ in range(100):
        client.get("/api/v1/spend/")

    # The budget is per user, not per endpoint: 101st request blocked anywhere.
    assert client.get("/api/v1/spend/").status_code == 429
    assert client.get("/api/v1/checks/").status_code == 429

    # A different user has their own independent budget.
    second_client, _ = _fresh_throttled_client(django_user_model, "seconduser")
    assert second_client.get("/api/v1/spend/").status_code == 200


def test_health_probe_is_never_throttled(client_fixture):
    client, _ = client_fixture
    for _ in range(100):
        client.get("/api/v1/spend/")

    # Even after the user's budget is exhausted, health stays answerable.
    assert client.get("/api/v1/health/").status_code == 200
