"""Check worker task (A4): the async half of the 202-then-poll contract.

Fail-state law (AGENTS.md §2) applies here too: a completed *fake* run must
never carry a real verdict. The placeholder marks runs `unverified` — a legal
VerdictEnum meaning exactly "no model judged this" — and Chunk B's
InferenceService.check() will replace this task body behind the same
name/signature/duration contract.
"""

import time

from django.conf import settings
from django.utils import timezone

from apps.checks.models import AuditLog, CheckRun, CheckRunStatus, VerdictEnum


def run_check(check_run_id: int) -> str:
    """Process one queued CheckRun; safe to retry (idempotent per run).

    Returns a short status string for the Django-Q2 result column.
    """
    run = CheckRun.objects.filter(pk=check_run_id).first()
    if run is None:
        return "missing-claim"  # deleted between enqueue and pickup; drop.

    if run.status != CheckRunStatus.QUEUED:
        return f"skipped[{run.status}]"  # never clobber an in-flight/finished run

    run.status = CheckRunStatus.RUNNING
    run.started_at = timezone.now()
    # Persist before the latency window: a worker crash mid-sleep must leave a
    # truthful "running" row behind, not an imaginary "queued" one.
    run.save(update_fields=["status", "started_at"])

    # Fake latency: stand-in for the 10-60 s real inference window (§2.2).
    fake_latency = float(getattr(settings, "FAKE_CHECK_LATENCY_S", 2.0))
    time.sleep(fake_latency)

    run.status = CheckRunStatus.OK
    run.verdict_enum = VerdictEnum.UNVERIFIED
    run.finished_at = timezone.now()
    run.latency_ms = int((run.finished_at - run.started_at).total_seconds() * 1000)
    run.save(
        update_fields=[
            "status",
            "verdict_enum",
            "finished_at",
            "latency_ms",
        ]
    )

    AuditLog.objects.create(
        check_run=run,
        event="fake_check_completed",
        json_payload={
            "note": "placeholder task until Chunk B InferenceService.check()",
            "fake_latency_s": fake_latency,
        },
    )
    return "ok"
