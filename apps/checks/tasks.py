"""Check worker task (A4, filled in by B + C): enrich -> infer -> persist.

Fail-state law (AGENTS.md §2) is the contract here: a run is only ever marked
with a *real* verdict when the inference service produced a validated one. A
provider outage, timeout, evidence-pipeline failure, or any unexpected exception
becomes an honest ``fail_state`` — never a fabricated verdict. The §2.2 envelope
(detail / retry_after / providers_tried) is written to ``AuditLog`` with event
``fail_state_entered``, the same shape ``CheckRunResultSerializer`` reads back.
"""

import logging

from django.conf import settings
from django.utils import timezone

from apps.checks.models import AuditLog, CheckRun, CheckRunStatus, VerdictEnum
from apps.inference.catalog import ModelCatalog
from apps.inference.providers.base import BaseLLMProvider
from apps.inference.providers.ollama import OllamaProvider
from apps.inference.providers.remote_api import RemoteLLMProvider
from apps.inference.service import InferenceService
from apps.inference.spend import SpendManager
from apps.inference.types import (
    DEFAULT_FAIL_RETRY_AFTER_S,
    FAIL_STATE,
    InferenceOutcome,
    InferenceResult,
)
from apps.sources.packer import store_evidence
from apps.sources.pipeline import run_evidence_pipeline

logger = logging.getLogger(__name__)

DEFAULT_SPEND_CAP_USD = 5.0

_RESULT_STATUS_MAP = {
    "ok": CheckRunStatus.OK,
    "fallback": CheckRunStatus.FALLBACK,
    "fail_state": CheckRunStatus.FAIL_STATE,
}

VALID_VERDICTS = frozenset(VerdictEnum.values)


def _build_prompt(claim: str, bundle) -> str:
    """Compose the user prompt: the claim plus the labelled evidence bundle."""
    block = bundle.as_prompt_block()
    return f"{claim}\n\nEvidence:\n{block}" if block else claim


def _remote_prices(model_id: str) -> tuple[float | None, float | None]:
    """Price a remote model in USD-per-million-tokens.

    Free tiers cost nothing; a paid model's price comes from the live (cached)
    OpenRouter catalog. Returning ``(None, None)`` makes the service skip the
    remote call rather than spend money against an unknown price.
    """
    if not model_id or model_id.lower().endswith(":free"):
        return 0.0, 0.0
    try:
        for info in ModelCatalog().get_remote_models():
            if info.model_id == model_id:
                return info.input_price_per_mtok, info.output_price_per_mtok
    except Exception as error:  # pragma: no cover - network failure path
        logger.warning("Catalog lookup failed for %s: %s", model_id, error)
    return None, None


def _tier_model(user, tier: str, default: str) -> str:
    return (
        user.model_settings.filter(tier=tier).values_list("model_id", flat=True).first()
        or default
    )


def _build_providers(run: CheckRun) -> list[BaseLLMProvider]:
    """Assemble the provider chain from the user's per-tier ``ModelSetting``.

    Remote is only included when an API key is configured; when it is absent the
    local Ollama tier is the sole (and therefore primary) provider. Model ids
    fall back to the safe defaults (the free Gemma and the canonical QAT tag).
    """
    user = run.claim.created_by
    providers: list[BaseLLMProvider] = []

    api_key = (getattr(settings, "OPENROUTER_API_KEY", "") or "").strip()
    if api_key:
        model_id = _tier_model(
            user,
            "api",
            getattr(settings, "DEFAULT_REMOTE_MODEL", "google/gemma-4-26b-a4b-it:free"),
        )
        input_price, output_price = _remote_prices(model_id)
        providers.append(
            RemoteLLMProvider(
                api_key=api_key,
                model_id=model_id,
                input_price_per_mtok=input_price,
                output_price_per_mtok=output_price,
            )
        )

    local_model = _tier_model(
        user,
        "local",
        getattr(settings, "DEFAULT_LOCAL_MODEL", "gemma4:e4b-it-qat"),
    )
    providers.append(
        OllamaProvider(
            base_url=getattr(settings, "OLLAMA_BASE_URL", "http://localhost:11434"),
            model_id=local_model,
        )
    )
    return providers


def _spend_cap(run: CheckRun) -> float:
    setting = run.claim.created_by.model_settings.filter(tier="api").first()
    if setting is not None and setting.spend_cap_monthly is not None:
        return float(setting.spend_cap_monthly)
    return DEFAULT_SPEND_CAP_USD


def _perform_inference(run: CheckRun) -> InferenceOutcome:
    """Enrich the claim (Chunk C) then run the fallback chain (Chunk B)."""
    bundle = run_evidence_pipeline(run.claim.text)
    store_evidence(run, bundle)
    prompt = _build_prompt(run.claim.text, bundle)
    providers = _build_providers(run)
    service = InferenceService(providers, spend_manager=SpendManager())
    return service.check(
        prompt,
        spend_scope=f"user-{run.claim.created_by_id}",
        monthly_spend_cap=_spend_cap(run),
    )


def _persist(run: CheckRun, outcome: InferenceOutcome) -> None:
    result = outcome.result
    run.status = _RESULT_STATUS_MAP[result.status]
    run.verdict_enum = VerdictEnum(result.verdict) if result.verdict in VALID_VERDICTS else None
    run.confidence = result.confidence
    run.provider_used = result.provider_used
    run.model_id = outcome.model_id
    run.tokens_in = outcome.tokens_in
    run.tokens_out = outcome.tokens_out
    run.price_in_per_mtok = outcome.price_in_per_mtok
    run.price_out_per_mtok = outcome.price_out_per_mtok
    run.finished_at = timezone.now()
    run.latency_ms = int((run.finished_at - run.started_at).total_seconds() * 1000)
    run.save(
        update_fields=[
            "status",
            "verdict_enum",
            "confidence",
            "provider_used",
            "model_id",
            "tokens_in",
            "tokens_out",
            "price_in_per_mtok",
            "price_out_per_mtok",
            "finished_at",
            "latency_ms",
        ]
    )

    if result.status == FAIL_STATE:
        AuditLog.objects.create(
            check_run=run,
            event="fail_state_entered",
            json_payload={
                "detail": outcome.detail,
                "retry_after": outcome.retry_after,
                "providers_tried": outcome.providers_tried,
            },
        )
    else:
        AuditLog.objects.create(
            check_run=run,
            event="check_completed",
            json_payload={
                "provider_used": result.provider_used,
                "model_id": outcome.model_id,
            },
        )


def _unexpected_failure(run: CheckRun, error: BaseException) -> InferenceOutcome:
    """Never fabricate: any unforeseen exception becomes an honest fail state."""
    logger.exception("Check %s failed unexpectedly", run.pk)
    result = InferenceResult(
        verdict=None,
        confidence=None,
        evidence=[],
        raw_model_output=None,
        provider_used=None,
        latency_ms=None,
        status=FAIL_STATE,
    )
    return InferenceOutcome(
        result=result,
        detail=f"Unexpected error during inference: {error}",
        retry_after=DEFAULT_FAIL_RETRY_AFTER_S,
        providers_tried=[],
    )


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
    # Persist before the (long) inference window: a worker crash mid-inference
    # must leave a truthful "running" row, never an imaginary "queued" one.
    run.save(update_fields=["status", "started_at"])

    try:
        outcome = _perform_inference(run)
    except Exception as error:  # noqa: BLE001 - any failure is a fail state, never a verdict
        outcome = _unexpected_failure(run, error)

    _persist(run, outcome)
    return outcome.result.status
