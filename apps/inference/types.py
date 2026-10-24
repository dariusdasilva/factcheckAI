from dataclasses import dataclass
from enum import Enum


class InferenceStatus(str, Enum):
    OK = "ok"
    FALLBACK = "fallback"
    FAIL_STATE = "fail_state"

@dataclass
class InferenceResult:
    """Validated verdict plus billing metadata for the downstream CheckRun."""

    verdict: str | None
    confidence: float
    evidence: list[str]
    raw_model_output: str
    provider_used: str
    latency_ms: int
    status: InferenceStatus
    detail: str | None = None
    retry_after: int | None = None
    providers_tried: list[str] | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    price_in_per_mtok: float | None = None
    price_out_per_mtok: float | None = None
    cost_usd: float | None = None

@dataclass
class ModelInfo:
    model_id: str
    context_window: int
    input_price_per_mtok: float
    output_price_per_mtok: float
    is_free: bool = False
    is_local: bool = False
    is_legacy: bool = False
