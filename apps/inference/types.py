"""Chunk B types + re-exports of the frozen inference contract.

The canonical ``InferenceResult`` is owned by Chunk A and frozen in
``apps.checks.contracts`` (WORK_CHUNKS.md "Interface A hands to B/C/D"). Chunk B
must consume it, never redefine it. This module re-exports it so the inference
package has a single import point, and adds B-only types (``ModelInfo`` from
the catalog, ``InferenceOutcome`` for billing + fail-state metadata) that are
*not* part of the frozen contract.
"""

from dataclasses import dataclass, field

from apps.checks.contracts import (  # noqa: F401  (re-exported for the package)
    DEFAULT_FAIL_RETRY_AFTER_S,
    DEFAULT_PROVIDERS_TRIED,
    FAIL_STATE_DETAIL,
    INFERENCE_RESULT_STATUSES,
    PROVIDER_OLLAMA,
    PROVIDER_REMOTE_API,
    InferenceResult,
)

# Terminal statuses, equal to the frozen INFERENCE_RESULT_STATUSES strings.
OK = "ok"
FALLBACK = "fallback"
FAIL_STATE = "fail_state"


@dataclass
class ModelInfo:
    """A single model as shown by the catalog/picker (§3.1)."""

    model_id: str
    context_window: int
    input_price_per_mtok: float
    output_price_per_mtok: float
    is_free: bool = False
    is_local: bool = False
    is_legacy: bool = False


@dataclass
class InferenceOutcome:
    """Service-level result: the canonical result plus billing/fail-state data.

    ``result`` is the frozen ``InferenceResult`` that Chunk A persists onto
    ``CheckRun``. The remaining fields are Chunk B's operational metadata that
    don't belong on the frozen type: per-call price snapshot (§3.1 ledger),
    token usage, and — when the run failed — the §2.2 fail-state envelope
    (detail / retry_after / providers_tried) that Chunk A writes to ``AuditLog``.
    """

    result: InferenceResult
    tokens_in: int | None = None
    tokens_out: int | None = None
    price_in_per_mtok: float | None = None
    price_out_per_mtok: float | None = None
    cost_usd: float | None = None
    detail: str | None = None
    retry_after: int | None = None
    providers_tried: list[str] = field(default_factory=list)
