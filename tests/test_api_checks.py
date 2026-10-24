"""A3 deliverable: checks API tests — 202-then-poll acceptance + contract
behaviour (WORK_CHUNKS.md Chunk A). Hermetic.

Auth for these tests: DRF force_authenticate (real session/token plumbing is
verified in smoke tests + A4's throttle suite).
"""

import pytest
from rest_framework.test import APIClient

from apps.checks.contracts import (
    DEFAULT_FAIL_RETRY_AFTER_S,
    FAIL_STATE_DETAIL,
    PROVIDER_OLLAMA,
    PROVIDER_REMOTE_API,
)
from apps.checks.models import (
    AuditLog,
    CheckRun,
    CheckRunStatus,
    Claim,
    Evidence,
    EvidenceHop,
    VerdictEnum,
)

pytestmark = [pytest.mark.django_db]

SUBMIT_URL = "/api/v1/checks/"
CLAIM = "Drinking coffee cures the common cold."
BODY = {"claim": CLAIM, "context": {"source_url": "https://example.com/article", "selection": True}}


@pytest.fixture()
def client_fixture(django_user_model):
    user = django_user_model.objects.create_user(username="webuser", password="x")
    client = APIClient()
    client.force_authenticate(user=user)
    return client, user


def test_202_then_poll_works(client_fixture):
    client, _ = client_fixture

    created = client.post(SUBMIT_URL, BODY, format="json")
    assert created.status_code == 202
    body = created.json()
    check_id = body["check_id"]
    assert body["status"] == CheckRunStatus.QUEUED
    assert isinstance(check_id, int)

    # Poll before the worker picks it up (queue wiring is A4).
    polled = client.get(f"{SUBMIT_URL}{check_id}/")
    assert polled.status_code == 200
    data = polled.json()
    assert data["check_id"] == check_id
    assert data["status"] == CheckRunStatus.QUEUED
    assert data["claim_text"] == CLAIM
    # progress runs must NOT carry the fail-state envelope keys
    assert "detail" not in data
    assert "retry_after" not in data
    assert "providers_tried" not in data


def test_submit_persists_claim_with_source_url_and_flags_queued(client_fixture):
    client, user = client_fixture
    created = client.post(SUBMIT_URL, BODY, format="json")
    assert created.status_code == 202
    claim = Claim.objects.get(created_by=user)
    assert claim.text == CLAIM
    assert claim.source_url == "https://example.com/article"


def test_submit_rejects_too_short_claim(client_fixture):
    client, _ = client_fixture
    response = client.post(SUBMIT_URL, {"claim": "  ab  "}, format="json")
    assert response.status_code == 400
    assert "claim" in response.json()


def test_submit_rejects_oversized_claim(client_fixture):
    client, _ = client_fixture
    response = client.post(SUBMIT_URL, {"claim": "x" * 4001}, format="json")
    assert response.status_code == 400


def test_poll_is_scoped_to_owning_user(client_fixture, django_user_model):
    client, _ = client_fixture
    check_id = client.post(SUBMIT_URL, BODY, format="json").json()["check_id"]

    stranger = django_user_model.objects.create_user(username="stranger", password="x")
    other = APIClient()
    other.force_authenticate(user=stranger)

    assert other.get(f"{SUBMIT_URL}{check_id}/").status_code == 404
    assert other.get(SUBMIT_URL).json()["count"] == 0


def test_list_returns_paginated_own_runs(client_fixture):
    client, user = client_fixture
    for i in range(3):
        claim = Claim.objects.create(text=f"claim {i}", created_by=user)
        CheckRun.objects.create(claim=claim)

    response = client.get(SUBMIT_URL)
    assert response.status_code == 200
    data = response.json()
    assert set(data) >= {"count", "results"}
    assert data["count"] == 3
    # newest first (serializer ordering = newest first)
    assert data["results"][0]["check_id"] > data["results"][-1]["check_id"]


def test_fail_state_poll_includes_contract_envelope(client_fixture):
    client, user = client_fixture
    claim = Claim.objects.create(text="fail case", created_by=user)
    run = CheckRun.objects.create(claim=claim, status=CheckRunStatus.FAIL_STATE)
    AuditLog.objects.create(
        check_run=run,
        event="fail_state_entered",
        json_payload={
            "providers_tried": [PROVIDER_REMOTE_API, PROVIDER_OLLAMA],
            "retry_after": DEFAULT_FAIL_RETRY_AFTER_S,
        },
    )
    Evidence.objects.create(
        check_run=run,
        hop=EvidenceHop.WIKI,
        url="https://en.wikipedia.org/wiki/Common_cold",
        snippet="hop-1 text",
    )

    response = client.get(f"{SUBMIT_URL}{run.pk}/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "fail_state"
    assert data["detail"] == FAIL_STATE_DETAIL
    assert data["retry_after"] == DEFAULT_FAIL_RETRY_AFTER_S
    assert data["providers_tried"] == [PROVIDER_REMOTE_API, PROVIDER_OLLAMA]
    assert data["evidence"][0]["hop"] == EvidenceHop.WIKI


def test_finished_run_poll_sets_verdict_shape(client_fixture):
    client, user = client_fixture
    claim = Claim.objects.create(text="ok case", created_by=user)
    run = CheckRun.objects.create(
        claim=claim,
        status=CheckRunStatus.OK,
        verdict_enum=VerdictEnum.FALSE,
        confidence=0.72,
        provider_used=PROVIDER_REMOTE_API,
        latency_ms=4200,
        finished_at=None,
    )
    data = client.get(f"{SUBMIT_URL}{run.pk}/").json()
    assert data["verdict_enum"] == "false"
    assert pytest.approx(data["confidence"], 0.001) == 0.72
    assert data["provider_used"] == PROVIDER_REMOTE_API
    assert "detail" not in data


def test_health_remains_public_without_auth():
    r = APIClient().get("/api/v1/health/")
    assert r.status_code == 200
