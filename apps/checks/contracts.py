"""Frozen interface contracts — A hands these to B/C/D (contract freeze, wk 2).

Shared law (AGENTS.md §2, WORK_CHUNKS.md cross-chunk rules):
- Status strings are exact: a finished inference run is `ok`, `fallback` or
  `fail_state` — never "error", never an invented verdict.
- The fail-state HTTP body shape is per ARCHITECTURE.md §2.2:
  {"status": "fail_state", "detail": ..., "retry_after": ..., "providers_tried": [...]}
Changes here are cross-chunk changes and need an all-hands call.
"""

from dataclasses import dataclass, field
from typing import Any

# Terminal inference statuses, exactly as CHUNK B's InferenceService.check()
# returns them and as the UI/extension (D) branch on.
INFERENCE_RESULT_STATUSES = ("ok", "fallback", "fail_state")

# Providers, as recorded in CheckRun.provider_used (§2.2 / §4).
PROVIDER_REMOTE_API = "remote_api"
PROVIDER_OLLAMA = "ollama"

# Fail-state response body constants (§2.2) — exact strings, shared with D.
FAIL_STATE_DETAIL = "Both inference providers are currently unavailable."
DEFAULT_FAIL_RETRY_AFTER_S = 60
DEFAULT_PROVIDERS_TRIED = (PROVIDER_REMOTE_API, PROVIDER_OLLAMA)


@dataclass
class InferenceResult:
    """Single canonical result type produced by the inference service (§2.2).

    Chunk B's providers return this; Chunk A persists it onto `CheckRun`; Chunk
    D renders from it. Field order/names are part of the frozen contract.
    """

    verdict: str | None
    confidence: float | None
    evidence: list[dict[str, Any]] = field(default_factory=list)
    raw_model_output: str | None = None
    provider_used: str | None = None
    latency_ms: int | None = None
    # Default is fail_state: an unset/attacked result must degrade, never pass.
    status: str = "fail_state"

    def __post_init__(self) -> None:
        if self.status not in INFERENCE_RESULT_STATUSES:
            raise ValueError(
                f"InferenceResult.status must be one of {INFERENCE_RESULT_STATUSES}, "
                f"got {self.status!r}"
            )
