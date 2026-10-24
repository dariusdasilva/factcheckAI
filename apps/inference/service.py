"""Provider fallback orchestration, circuit breaking, deadlines, and spend caps.

The service's public entry point ``check`` returns an ``InferenceOutcome`` whose
``.result`` is the frozen ``InferenceResult``. The frozen type carries only the
verdict contract; billing (price snapshot, token usage, cost) and the §2.2
fail-state envelope (detail/retry_after/providers_tried) ride on ``InferenceOutcome``
so Chunk A can persist them onto ``CheckRun``/``AuditLog`` without touching the
frozen contract.
"""

import logging
import math
import queue
import threading
import time

from apps.inference.output import SYSTEM_PROMPT
from apps.inference.providers.base import BaseLLMProvider
from apps.inference.spend import CostEstimator, SpendManager
from apps.inference.types import (
    DEFAULT_FAIL_RETRY_AFTER_S,
    FAIL_STATE,
    FALLBACK,
    PROVIDER_REMOTE_API,
    InferenceOutcome,
    InferenceResult,
)

logger = logging.getLogger(__name__)


class ProviderCallTimeout(TimeoutError):
    """Raised when a provider call exceeds the service's remaining deadline."""


class CircuitBreaker:
    """Three consecutive failures open the breaker for the configured cooldown."""

    def __init__(self, failure_threshold: int = 3, cooldown_period: int = 60):
        if failure_threshold < 1 or cooldown_period < 1:
            raise ValueError("Circuit-breaker threshold and cooldown must be positive")
        self.failure_threshold = failure_threshold
        self.cooldown_period = cooldown_period
        self.failures: dict[str, int] = {}
        self.cooldown_until: dict[str, float] = {}
        self._probe_in_flight: set[str] = set()
        self._lock = threading.Lock()

    def record_failure(self, provider_id: str) -> None:
        with self._lock:
            failures = self.failures.get(provider_id, 0) + 1
            self.failures[provider_id] = failures
            self._probe_in_flight.discard(provider_id)
            if failures >= self.failure_threshold:
                self.cooldown_until[provider_id] = time.monotonic() + self.cooldown_period
                logger.warning(
                    "Circuit breaker tripped for %s; cooldown is %ss",
                    provider_id,
                    self.cooldown_period,
                )

    def record_success(self, provider_id: str) -> None:
        with self._lock:
            self.failures[provider_id] = 0
            self.cooldown_until.pop(provider_id, None)
            self._probe_in_flight.discard(provider_id)

    def cancel_probe(self, provider_id: str) -> None:
        """Release a half-open slot when no provider request was actually made."""
        with self._lock:
            self._probe_in_flight.discard(provider_id)

    def is_available(self, provider_id: str) -> bool:
        """Allow a single half-open probe after a provider's cooldown expires."""
        with self._lock:
            cooldown = self.cooldown_until.get(provider_id)
            if cooldown is None:
                return True
            now = time.monotonic()
            if now < cooldown or provider_id in self._probe_in_flight:
                return False
            self._probe_in_flight.add(provider_id)
            return True

    def retry_after(self, provider_ids: list[str]) -> int:
        with self._lock:
            delays = [
                max(0, math.ceil(until - time.monotonic()))
                for provider_id, until in self.cooldown_until.items()
                if provider_id in provider_ids
            ]
        return max(delays, default=DEFAULT_FAIL_RETRY_AFTER_S)


def _call_with_deadline(provider: BaseLLMProvider, prompt: str, timeout: float):
    """Run a potentially slow provider in a daemon thread and enforce wall time."""
    result_queue: queue.Queue = queue.Queue(maxsize=1)

    def invoke() -> None:
        try:
            result_queue.put((True, provider.check(prompt, timeout=timeout)))
        except BaseException as error:  # propagate provider exceptions to caller
            result_queue.put((False, error))

    worker = threading.Thread(target=invoke, daemon=True, name="inference-provider-call")
    worker.start()
    worker.join(timeout)
    if worker.is_alive():
        raise ProviderCallTimeout(f"Provider exceeded {timeout:.2f}s deadline")
    succeeded, value = result_queue.get_nowait()
    if not succeeded:
        raise value
    return value


class InferenceService:
    """Orchestrate Remote API -> Ollama -> explicit fail state (§2.2)."""

    TOTAL_TIMEOUT_SECONDS = 90.0

    def __init__(
        self,
        providers: list[BaseLLMProvider],
        spend_manager: SpendManager | None = None,
        *,
        total_timeout_seconds: float = TOTAL_TIMEOUT_SECONDS,
        circuit_breaker: CircuitBreaker | None = None,
    ):
        if total_timeout_seconds <= 0:
            raise ValueError("Total inference timeout must be positive")
        self.providers = providers
        self.circuit_breaker = circuit_breaker or CircuitBreaker()
        self.spend_manager = spend_manager or SpendManager()
        self.cost_estimator = CostEstimator()
        self.total_timeout_seconds = total_timeout_seconds

    @staticmethod
    def _provider_id(provider: BaseLLMProvider) -> str:
        return getattr(provider, "provider_id", provider.__class__.__name__)

    def _fail_state(
        self,
        started: float,
        providers_tried: list[str],
        detail: str,
    ) -> InferenceOutcome:
        result = InferenceResult(
            verdict=None,
            confidence=None,
            evidence=[],
            raw_model_output=None,
            provider_used=None,
            latency_ms=int((time.monotonic() - started) * 1000),
            status=FAIL_STATE,
        )
        return InferenceOutcome(
            result=result,
            detail=detail,
            retry_after=self.circuit_breaker.retry_after(providers_tried),
            providers_tried=providers_tried,
        )

    def check(
        self,
        prompt: str,
        remote_input_price: float | None = None,
        remote_output_price: float | None = None,
        *,
        spend_scope: str = "default",
        monthly_spend_cap: float | None = None,
    ) -> InferenceOutcome:
        started = time.monotonic()
        providers_tried: list[str] = []
        if not self.providers:
            return self._fail_state(
                started, providers_tried, "No inference providers are configured."
            )

        # The remote (paid) tier is whichever provider is marked PROVIDER_REMOTE_API,
        # not necessarily ``providers[0]`` — a local-only deployment has no remote.
        remote = next(
            (p for p in self.providers if self._provider_id(p) == PROVIDER_REMOTE_API),
            None,
        )
        has_remote_tier = remote is not None
        remote_price_known = False
        estimated_cost = 0.0
        input_price = output_price = None
        if remote is not None:
            input_price = (
                remote_input_price
                if remote_input_price is not None
                else getattr(remote, "input_price_per_mtok", None)
            )
            output_price = (
                remote_output_price
                if remote_output_price is not None
                else getattr(remote, "output_price_per_mtok", None)
            )
            if input_price is not None and output_price is not None:
                estimated_cost = self.cost_estimator.estimate_cost(
                    f"{SYSTEM_PROMPT}\n{prompt}", input_price, output_price
                )
                remote_price_known = True
            else:
                logger.warning("Skipping remote provider because its model price is unknown")

        reservation_made = False

        for provider in self.providers:
            provider_id = self._provider_id(provider)
            providers_tried.append(provider_id)
            is_remote_tier = provider is remote

            if is_remote_tier and not remote_price_known:
                continue
            if not self.circuit_breaker.is_available(provider_id):
                continue

            if is_remote_tier:
                try:
                    reservation_made = self.spend_manager.reserve(
                        estimated_cost,
                        spend_scope,
                        monthly_cap=monthly_spend_cap,
                    )
                except Exception as error:
                    logger.error(
                        "Cannot verify API spend cap; skipping remote provider: %s", error
                    )
                    reservation_made = False
                    self.circuit_breaker.cancel_probe(provider_id)
                if not reservation_made:
                    self.circuit_breaker.cancel_probe(provider_id)
                    logger.info("Monthly API spend cap reached; skipping remote provider")
                    continue

            remaining = self.total_timeout_seconds - (time.monotonic() - started)
            if remaining <= 0:
                if is_remote_tier and reservation_made:
                    self.spend_manager.adjust_spend(-estimated_cost, spend_scope)
                    reservation_made = False
                self.circuit_breaker.cancel_probe(provider_id)
                break

            try:
                result = _call_with_deadline(provider, prompt, remaining)
                elapsed = time.monotonic() - started
                if elapsed > self.total_timeout_seconds:
                    raise ProviderCallTimeout("Total inference deadline exceeded")
                if not isinstance(result, InferenceResult):
                    raise TypeError("Provider returned an invalid inference result")
                if result.status == FAIL_STATE or result.verdict is None:
                    raise ValueError("Provider returned no validated verdict")

                self.circuit_breaker.record_success(provider_id)
                result.provider_used = provider_id
                result.latency_ms = int(elapsed * 1000)
                # "fallback" means we fell back to local because a remote tier exists.
                if not is_remote_tier and has_remote_tier:
                    result.status = FALLBACK

                model_id = getattr(provider, "model_id", None)
                tokens_in, tokens_out = getattr(provider, "last_usage", (None, None))

                if is_remote_tier:
                    if tokens_in is not None and tokens_out is not None:
                        actual_cost = self.cost_estimator.cost_for_tokens(
                            tokens_in, tokens_out, input_price, output_price
                        )
                    else:
                        actual_cost = estimated_cost
                    self.spend_manager.adjust_spend(actual_cost - estimated_cost, spend_scope)
                    reservation_made = False
                    cost_usd = actual_cost
                    price_in, price_out = input_price, output_price
                else:
                    cost_usd = 0.0
                    price_in = price_out = None

                return InferenceOutcome(
                    result=result,
                    model_id=model_id,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    price_in_per_mtok=price_in,
                    price_out_per_mtok=price_out,
                    cost_usd=cost_usd,
                    providers_tried=providers_tried,
                )
            except Exception as error:
                logger.warning("Provider %s failed: %s", provider_id, error)
                self.circuit_breaker.record_failure(provider_id)
                if is_remote_tier and reservation_made:
                    self.spend_manager.adjust_spend(-estimated_cost, spend_scope)
                    reservation_made = False
                if isinstance(error, ProviderCallTimeout):
                    break

        if reservation_made:
            self.spend_manager.adjust_spend(-estimated_cost, spend_scope)
        return self._fail_state(
            started,
            providers_tried,
            "Inference providers are currently unavailable or the request exceeded its time limit.",
        )
