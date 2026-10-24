"""A3 tests: API key creation (hashed-only storage) + source cache push."""

import hashlib

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import ApiKey
from apps.checks.models import EvidenceFetchStatus, Source

pytestmark = [pytest.mark.django_db]

SOURCE_URL = "https://example.com/article"
SOURCE_TEXT = "The article text the extension captured on this page."


@pytest.fixture()
def client_fixture(django_user_model):
    user = django_user_model.objects.create_user(username="keysuser", password="x")
    client = APIClient()
    client.force_authenticate(user=user)
    return client, user


def test_create_api_key_shows_raw_once_stores_hash_only(client_fixture):
    client, user = client_fixture
    response = client.post("/api/v1/auth/keys/")
    assert response.status_code == 201
    body = response.json()
    assert body["key"].startswith("fcai_")
    # returned in response so listing UIs can show key age without re-querying
    assert "created_at" in body
    from datetime import datetime

    assert datetime.fromisoformat(body["created_at"]).tzinfo is not None

    stored = ApiKey.objects.get(pk=body["id"])
    assert stored.key_hash == hashlib.sha256(body["key"].encode()).hexdigest()
    assert stored.is_active


def test_create_api_key_multiple_keys_unique_hashes(client_fixture):
    client, user = client_fixture
    first = client.post("/api/v1/auth/keys/").json()
    second = client.post("/api/v1/auth/keys/").json()
    assert first["key"] != second["key"]
    assert ApiKey.objects.filter(user=user).count() == 2
    hashes = set(ApiKey.objects.values_list("key_hash", flat=True))
    assert len(hashes) == 2


def test_source_push_creates_cache_row(client_fixture):
    client, _ = client_fixture
    response = client.post(
        "/api/v1/sources/",
        {"url": SOURCE_URL, "text": SOURCE_TEXT},
        format="json",
    )
    assert response.status_code == 201
    body = response.json()
    assert body["cached"] is False

    row = Source.objects.get(pk=body["id"])
    assert row.url == SOURCE_URL
    assert row.domain == "example.com"
    assert row.fetch_status == EvidenceFetchStatus.FETCHED
    assert row.text_extract == SOURCE_TEXT
    expected_hash = hashlib.sha256(SOURCE_TEXT.encode()).hexdigest()
    assert row.content_hash == expected_hash
    assert row.fetched_at is not None  # the §3.2 staleness check needs this


def test_source_update_persists_fetch_status_and_fetched_at(client_fixture):
    # Audit finding #1: on update, both fields must actually be written —
    # this is where Chunk C's "fresh cache row" predicate lives.
    client, _ = client_fixture
    from django.utils import timezone

    first = client.post(
        "/api/v1/sources/",
        {"url": SOURCE_URL, "text": "version 1"},
        format="json",
    ).json()
    first_fetched_at = Source.objects.get(pk=first["id"]).fetched_at
    assert first_fetched_at > timezone.now() - timezone.timedelta(seconds=10)

    # Simulate a previously-errored row state, as if Chunk C's crawler hit a
    # 403 paywall and the extension re-pushes the same URL afterwards.
    row = Source.objects.get(pk=first["id"])
    row.fetch_status = EvidenceFetchStatus.ERROR
    row.fetched_at = None
    row.save()

    response = client.post(
        "/api/v1/sources/",
        {"url": SOURCE_URL, "text": "version 2"},
        format="json",
    )
    assert response.status_code == 200
    assert response.json()["cached"] is True

    fresh = Source.objects.get(pk=first["id"])
    assert fresh.fetch_status == EvidenceFetchStatus.FETCHED
    assert fresh.content_hash == hashlib.sha256(b"version 2").hexdigest()
    assert fresh.fetched_at is not None
    assert fresh.fetched_at > timezone.now() - timezone.timedelta(seconds=10)


def test_source_push_same_url_and_text_is_a_cache_hit(client_fixture):
    client, _ = client_fixture
    payload = {"url": SOURCE_URL, "text": SOURCE_TEXT}
    first = client.post("/api/v1/sources/", payload, format="json").json()
    second = client.post("/api/v1/sources/", payload, format="json").json()

    assert second["id"] == first["id"]
    assert second["cached"] is True
    assert Source.objects.count() == 1


def test_source_push_same_url_new_text_updates_cache(client_fixture):
    client, _ = client_fixture
    client.post("/api/v1/sources/", {"url": SOURCE_URL, "text": "v1"}, format="json")
    result = client.post("/api/v1/sources/", {"url": SOURCE_URL, "text": "v2"}, format="json")
    assert result.status_code == 200

    row = Source.objects.get(url=SOURCE_URL)
    assert row.content_hash == hashlib.sha256(b"v2").hexdigest()


def test_source_push_rejects_oversized_text(client_fixture):
    client, _ = client_fixture
    response = client.post(
        "/api/v1/sources/",
        {"url": SOURCE_URL, "text": "x" * 1_000_001},
        format="json",
    )
    assert response.status_code == 400


def test_endpoints_require_authentication(django_user_model):
    # DRF nuance: fully anonymous requests get 403 when no authenticator
    # advertises a challenge (session auth doesn't); 401 is for bad
    # credentials. D must treat both as "not logged in".
    def denied(response) -> bool:
        return response.status_code in (401, 403)

    anon = APIClient()
    assert denied(anon.post("/api/v1/checks/", {"claim": "totally unrelated claim"}, format="json"))
    assert denied(anon.post("/api/v1/auth/keys/"))
    assert denied(anon.post("/api/v1/sources/", {"url": SOURCE_URL, "text": "t"}, format="json"))
    assert denied(anon.put("/api/v1/settings/model/", {"tier": "api", "model_id": "m"}, format="json"))
    assert denied(anon.get("/api/v1/spend/"))
    assert anon.get("/api/v1/health/").status_code == 200
