"""A4 + B/C integration: the check worker runs evidence -> inference -> persist.

Hermetic: ``run_check`` is invoked directly (as the qcluster would) with
``_perform_inference`` patched out, so no network is touched here. The real
evidence pipeline (Chunk C) and inference service (Chunk B) are covered by their
own hermetic suites; these tests pin the worker plumbing and the fail-state law
(AGENTS.md §2 — a run never carries a fabricated verdict).
"""

import pytest
from rest_framework.test import APIClient

from apps.checks.models import AuditLog, CheckRun, CheckRunStatus, Claim, VerdictEnum
from apps.checks.tasks import run_check
from apps.inference.types import InferenceOutcome, InferenceResult

pytestmark = [pytest.mark.django_db]


@pytest.fixture(name="user")
def user_fixture(django_user_model):
    return django_user_model.objects.create_user(username="workeruser", password="x")


@pytest.fixture(name="queued_run")
def queued_run_fixture(user):
    claim = Claim.objects.create(text="the integration claim", created_by=user)
    return CheckRun.objects.create(claim=claim)


def ok_outcome(verdict="true", provider="remote_api", model="google/gemma-4-26b-a4b-it:free"):
    result = InferenceResult(
        verdict=verdict,
        confidence=0.9,
        evidence=[{"id": "W1", "hop": "wiki"}],
        raw_model_output='{"verdict":"true"}',
        provider_used=provider,
        latency_ms=100,
        status="ok",
    )
    return InferenceOutcome(
        result=result,
        model_id=model,
        tokens_in=100,
        tokens_out=50,
        price_in_per_mtok=0.0,
        price_out_per_mtok=0.0,
        cost_usd=0.0,
        providers_tried=[provider],
    )


def fail_outcome(detail="Both inference providers are currently unavailable."):
    result = InferenceResult(verdict=None, confidence=None, evidence=[], status="fail_state")
    return InferenceOutcome(
        result=result,
        detail=detail,
        retry_after=60,
        providers_tried=["remote_api", "ollama"],
    )


def test_check_completes_and_persists_a_real_verdict(queued_run, monkeypatch):
    monkeypatch.setattr("apps.checks.tasks._perform_inference", lambda run: ok_outcome())

    status = run_check(queued_run.pk)

    run = CheckRun.objects.get(pk=queued_run.pk)
    assert status == "ok"
    assert run.status == CheckRunStatus.OK
    assert run.verdict_enum == VerdictEnum.TRUE
    assert run.provider_used == "remote_api"
    assert run.model_id == "google/gemma-4-26b-a4b-it:free"
    assert run.confidence == pytest.approx(0.9)
    assert run.finished_at >= run.started_at
    assert run.latency_ms >= 0
    assert AuditLog.objects.filter(check_run=run, event="check_completed").exists()


def test_fail_state_never_fabricates_a_verdict(queued_run, monkeypatch):
    monkeypatch.setattr("apps.checks.tasks._perform_inference", lambda run: fail_outcome())

    run_check(queued_run.pk)

    run = CheckRun.objects.get(pk=queued_run.pk)
    assert run.status == CheckRunStatus.FAIL_STATE
    assert run.verdict_enum is None
    assert run.provider_used is None
    assert run.confidence is None
    log = AuditLog.objects.get(check_run=run, event="fail_state_entered")
    assert log.json_payload["providers_tried"] == ["remote_api", "ollama"]
    assert log.json_payload["retry_after"] == 60


def test_unexpected_error_becomes_honest_fail_state(queued_run, monkeypatch):
    def blow_up(run):
        raise RuntimeError("boom")

    monkeypatch.setattr("apps.checks.tasks._perform_inference", blow_up)

    run_check(queued_run.pk)

    run = CheckRun.objects.get(pk=queued_run.pk)
    assert run.status == CheckRunStatus.FAIL_STATE
    assert run.verdict_enum is None
    assert AuditLog.objects.filter(check_run=run, event="fail_state_entered").exists()


def test_perform_inference_uses_the_pipeline_bundle(queued_run, monkeypatch):
    """The real enrichment path extracts the bundle from the pipeline result."""
    from apps.inference.providers.base import BaseLLMProvider
    from apps.sources.packer import EvidenceBundle, PackedEvidence
    from apps.sources.pipeline import EvidencePipelineResult

    class FakeProvider(BaseLLMProvider):
        provider_id = "remote_api"
        input_price_per_mtok = 1.0
        output_price_per_mtok = 1.0
        model_id = "google/gemma-4-26b-a4b-it:free"

        def __init__(self):
            self.last_usage = (10, 5)
            self.seen_prompt = None

        def check(self, prompt, timeout=None):
            self.seen_prompt = prompt
            return InferenceResult(
                verdict="true",
                confidence=0.8,
                evidence=[{"id": "W1", "hop": "wiki"}],
                raw_model_output="",
                provider_used="remote_api",
                latency_ms=1,
                status="ok",
            )

        def is_available(self):
            return True

    bundle = EvidenceBundle(
        claim=queued_run.claim.text,
        items=[
            PackedEvidence(
                label="W1",
                hop="wiki",
                url="https://en.wikipedia.org/wiki/Coffee",
                title="Coffee",
                snippet="Coffee is a brewed drink.",
                relevance=0.9,
            )
        ],
    )
    pipeline_result = EvidencePipelineResult(claim=queued_run.claim.text, bundle=bundle)
    monkeypatch.setattr(
        "apps.checks.tasks.run_evidence_pipeline", lambda claim: pipeline_result
    )
    provider = FakeProvider()
    monkeypatch.setattr("apps.checks.tasks._build_providers", lambda run: [provider])

    from apps.checks.tasks import _perform_inference

    outcome = _perform_inference(queued_run)

    assert outcome.result.verdict == "true"
    assert "[W1]" in provider.seen_prompt
    assert queued_run.evidence.count() == 1  # store_evidence persisted the hop-1 row


def test_worker_never_clobbers_non_queued_runs(user):
    claim = Claim.objects.create(text="in-flight claim", created_by=user)
    run = CheckRun.objects.create(claim=claim, status=CheckRunStatus.RUNNING)

    assert run_check(run.pk) == f"skipped[{CheckRunStatus.RUNNING}]"
    run.refresh_from_db()
    assert run.status == CheckRunStatus.RUNNING


def test_worker_silently_drops_missing_runs():
    assert run_check(424242) == "missing-claim"


def test_running_is_persisted_before_inference(queued_run, monkeypatch):
    # A hard worker kill (SystemExit) mid-inference must leave a truthful
    # "running" row, never a stale "queued" one.
    observed_status = {}

    def crash(run):
        observed_status["crash"] = CheckRun.objects.get(pk=run.pk).status
        raise SystemExit("simulated worker kill")

    monkeypatch.setattr("apps.checks.tasks._perform_inference", crash)

    with pytest.raises(SystemExit, match="simulated worker kill"):
        run_check(queued_run.pk)

    assert observed_status["crash"] == CheckRunStatus.RUNNING
    assert CheckRun.objects.get(pk=queued_run.pk).status == CheckRunStatus.RUNNING


def test_submit_enqueues_task_on_the_orm_broker(django_user_model):
    enqueue_user = django_user_model.objects.create_user(username="enqueueuser", password="x")
    client = APIClient()
    client.force_authenticate(user=enqueue_user)

    from django_q.models import OrmQ

    response = client.post("/api/v1/checks/", {"claim": "enqueue me"}, format="json")
    assert response.status_code == 202
    assert OrmQ.objects.count() == 1  # queued on the DB-backed broker (CI_CD.md)
