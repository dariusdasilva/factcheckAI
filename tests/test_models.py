"""A2 deliverable: model tests for the core tables (ARCHITECTURE.md §4).

Hermetic: stock Django + in-memory data only, no network, no fixtures.
"""

import hashlib

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.models import ApiKey, ModelSetting
from apps.checks.contracts import (
    INFERENCE_RESULT_STATUSES,
    PROVIDER_OLLAMA,
    PROVIDER_REMOTE_API,
    InferenceResult,
)
from apps.checks.models import (
    AuditLog,
    CheckRun,
    CheckRunStatus,
    Claim,
    Evidence,
    EvidenceFetchStatus,
    EvidenceHop,
    Source,
    VerdictEnum,
)

pytestmark = [pytest.mark.django_db]


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user(username="chunk-a", password="x")


# --- Frozen contract law --------------------------------------------------

def test_inference_result_rejects_unknown_status():
    with pytest.raises(ValueError, match="fail_state"):
        InferenceResult(verdict=None, confidence=None, status="error")


def test_inference_result_default_status_is_fail_state():
    # Default-safe: an unset/unvalidated result must degrade, never pass.
    result = InferenceResult(verdict=None, confidence=None)
    assert result.status == "fail_state"


def test_inference_result_accepts_all_contract_statuses():
    for status in ("ok", "fallback", "fail_state"):
        result = InferenceResult(verdict="unverified", confidence=0.5, status=status)
        assert result.status == status


def test_checkrun_carries_progress_plus_contract_statuses():
    progress = {"queued", "running"}
    assert progress <= set(CheckRunStatus.values)
    assert {"ok", "fallback", "fail_state"} <= set(CheckRunStatus.values)
    assert INFERENCE_RESULT_STATUSES == ("ok", "fallback", "fail_state")


def test_provider_constants_match_contract():
    assert PROVIDER_REMOTE_API == "remote_api"
    assert PROVIDER_OLLAMA == "ollama"


# --- checks app models ----------------------------------------------------

def test_claim_str_clips_long_text(user):
    claim = Claim.objects.create(text="x" * 200, created_by=user)
    rendered = str(claim)
    assert len(rendered) < len(claim.text)
    assert rendered.startswith(f"{claim.pk}: xxx")


def test_checkrun_defaults_to_queued(user):
    claim = Claim.objects.create(text="Water boils at 90°C.", created_by=user)
    run = CheckRun.objects.create(claim=claim)
    assert run.status == CheckRunStatus.QUEUED
    assert run.created_at is not None


def test_checkrun_persists_cost_snapshot_fields(user):
    claim = Claim.objects.create(text="Coffee cures colds.", created_by=user)
    run = CheckRun.objects.create(
        claim=claim,
        status=CheckRunStatus.OK,
        provider_used=PROVIDER_REMOTE_API,
        model_id="google/gemma-4-26b-a4b-it:free",
        tokens_in=3000,
        tokens_out=512,
        price_in_per_mtok="0.067500",
        price_out_per_mtok="0.225000",
        confidence=0.72,
        verdict_enum=VerdictEnum.FALSE,
        latency_ms=4200,
        started_at=timezone.now(),
        finished_at=timezone.now(),
    )
    refresh = CheckRun.objects.get(pk=run.pk)
    assert str(refresh.price_in_per_mtok) == "0.067500"
    assert refresh.verdict_enum == "false"
    assert refresh.latency_ms == 4200


def test_checkrun_confidence_validator_bounds(user):
    claim = Claim.objects.create(text="Bounds test.", created_by=user)
    run = CheckRun(claim=claim, confidence=1.4)
    with pytest.raises(ValidationError):
        run.full_clean()


def test_evidence_rows_cascade_with_check_run(user):
    claim = Claim.objects.create(text="Cascade test.", created_by=user)
    run = CheckRun.objects.create(claim=claim)
    Evidence.objects.create(
        check_run=run,
        hop=EvidenceHop.WIKI,
        url="https://en.wikipedia.org/wiki/Boiling_point",
        snippet="hop-1 text",
        relevance=0.8,
    )
    AuditLog.objects.create(
        check_run=run,
        event="fallback_used",
        json_payload={"providers_tried": [PROVIDER_REMOTE_API, PROVIDER_OLLAMA]},
    )
    run.delete()
    assert Evidence.objects.count() == 0
    assert AuditLog.objects.count() == 0


def test_evidence_hop_choices_support_two_hop_crawl():
    assert {"wiki", "cited_source"} <= set(EvidenceHop.values)


def test_source_url_is_unique():
    Source.objects.create(
        url="https://en.wikipedia.org/wiki/Boiling_point",
        content_hash="a" * 64,
        domain="en.wikipedia.org",
        fetch_status=EvidenceFetchStatus.FETCHED,
        text_extract="cached text",
        fetched_at=timezone.now(),
    )
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Source.objects.create(
                url="https://en.wikipedia.org/wiki/Boiling_point",
                content_hash="b" * 64,
                domain="en.wikipedia.org",
            )


def test_audit_log_round_trips_json_payload(user):
    claim = Claim.objects.create(text="Payload test.", created_by=user)
    run = CheckRun.objects.create(claim=claim)
    AuditLog.objects.create(
        check_run=run,
        event="fail_state_entered",
        json_payload={"providers_tried": ["remote_api", "ollama"], "retry_after": 60},
    )
    stored = AuditLog.objects.get(check_run=run, event="fail_state_entered")
    assert stored.json_payload["retry_after"] == 60
    assert stored.json_payload["providers_tried"] == ["remote_api", "ollama"]


# --- accounts app models --------------------------------------------------


def test_api_key_hashing_is_sha256_and_deterministic(user):
    raw = "unit-test-raw-key"
    key = ApiKey.objects.create(user=user, key_hash=ApiKey.hash_key(raw))
    assert key.key_hash == hashlib.sha256(raw.encode()).hexdigest()


def test_api_key_revoke_sets_revoked_at(user):
    key = ApiKey.objects.create(user=user, key_hash=ApiKey.hash_key("to-revoke"))
    assert key.is_active
    key.revoke()
    assert not key.is_active
    assert key.revoked_at is not None


def test_modelsetting_one_row_per_user_per_tier(user):
    ModelSetting.objects.create(
        user=user, tier=ModelSetting.Tier.API, model_id="google/gemma-4-26b-a4b-it:free"
    )
    ModelSetting.objects.create(
        user=user, tier=ModelSetting.Tier.LOCAL, model_id="gemma4:e4b-it-qat"
    )
    # Same (user, tier) twice must be rejected.
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            ModelSetting.objects.create(
                user=user, tier=ModelSetting.Tier.API, model_id="google/gemma-3-4b-it"
            )


def test_modelsetting_null_spend_cap_is_allowed_and_tier_checked(user):
    local = ModelSetting.objects.create(
        user=user, tier=ModelSetting.Tier.LOCAL, model_id="gemma4:e4b-it-qat"
    )
    assert local.spend_cap_monthly is None
    capped = ModelSetting.objects.create(
        user=user,
        tier=ModelSetting.Tier.API,
        model_id="google/gemma-4-26b-a4b-it:free",
        spend_cap_monthly="5.00",
    )
    assert str(capped.spend_cap_monthly) == "5.00"
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            ModelSetting.objects.create(user=user, tier="other", model_id="anything")
