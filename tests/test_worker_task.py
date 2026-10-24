"""A4 deliverable: task-queue tests — slow fake check completes; worker is
idempotent; submits land on the ORM broker. Hermetic (no live worker needed:
run_check is invoked directly, as the qcluster would)."""

import time

import pytest
from rest_framework.test import APIClient

from apps.checks.models import (
    AuditLog,
    CheckRun,
    CheckRunStatus,
    Claim,
    VerdictEnum,
)
from apps.checks.tasks import run_check

pytestmark = [pytest.mark.django_db]


@pytest.fixture(name="user")
def user_fixture(django_user_model):
    return django_user_model.objects.create_user(username="workeruser", password="x")


@pytest.fixture(name="queued_run")
def queued_run_fixture(user):
    claim = Claim.objects.create(text="the fake check claim", created_by=user)
    return CheckRun.objects.create(claim=claim)


def test_slow_fake_check_task_completes(queued_run, settings):
    # Acceptance test: the slow fake-check task completes.
    settings.FAKE_CHECK_LATENCY_S = 0.4
    started_wall = time.monotonic()

    result = run_check(queued_run.pk)
    elapsed = time.monotonic() - started_wall

    assert result == "ok"
    assert elapsed >= 0.4
    run = CheckRun.objects.get(pk=queued_run.pk)
    assert run.status == CheckRunStatus.OK
    assert run.verdict_enum == VerdictEnum.UNVERIFIED
    assert run.started_at is not None
    assert run.finished_at is not None
    assert run.finished_at >= run.started_at
    assert run.latency_ms >= 350


def test_completed_run_is_never_a_fabricated_verdict(queued_run, settings):
    # Fail-state law: the plumbing placeholder must not invent confidence or
    # provider attribution — 'unverified' with no model data is the honest mark.
    settings.FAKE_CHECK_LATENCY_S = 0
    run_check(queued_run.pk)
    run = CheckRun.objects.get(pk=queued_run.pk)
    assert run.verdict_enum == VerdictEnum.UNVERIFIED
    assert run.provider_used is None
    assert run.confidence is None
    assert AuditLog.objects.filter(
        check_run=run, event="fake_check_completed"
    ).exists()


def test_worker_never_clobbers_non_queued_runs(user, settings):
    settings.FAKE_CHECK_LATENCY_S = 0
    claim = Claim.objects.create(text="in-flight claim", created_by=user)
    run = CheckRun.objects.create(claim=claim, status=CheckRunStatus.RUNNING)

    assert run_check(run.pk) == f"skipped[{CheckRunStatus.RUNNING}]"
    run.refresh_from_db()
    assert run.status == CheckRunStatus.RUNNING


def test_worker_silently_drops_missing_runs():
    assert run_check(424242) == "missing-claim"


def test_running_is_persisted_before_the_latency_window(queued_run, settings, monkeypatch):
    # Audit finding #4: status/started_at must hit the DB before time.sleep,
    # so a worker crash leaves a truthful "running" row, not a stale "queued".
    settings.FAKE_CHECK_LATENCY_S = 0
    observed_status = {}

    def crash_during_sleep(_seconds):
        observed_status["crash"] = CheckRun.objects.get(pk=queued_run.pk).status
        raise RuntimeError("simulated worker kill")

    monkeypatch.setattr("apps.checks.tasks.time.sleep", crash_during_sleep)

    with pytest.raises(RuntimeError, match="simulated worker kill"):
        run_check(queued_run.pk)

    assert observed_status["crash"] == CheckRunStatus.RUNNING
    # Row stays running after the crash — never silently reset to queued.
    assert CheckRun.objects.get(pk=queued_run.pk).status == CheckRunStatus.RUNNING


def test_submit_enqueues_task_on_the_orm_broker(django_user_model):
    enqueue_user = django_user_model.objects.create_user(username="enqueueuser", password="x")
    client = APIClient()
    client.force_authenticate(user=enqueue_user)

    from django_q.models import OrmQ

    response = client.post(
        "/api/v1/checks/",
        {"claim": "enqueue me"},
        format="json",
    )
    assert response.status_code == 202
    assert OrmQ.objects.count() == 1  # queued on the DB-backed broker (CI_CD.md)
