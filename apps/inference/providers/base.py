from abc import ABC, abstractmethod

from apps.inference.types import InferenceResult


class BaseLLMProvider(ABC):
    """Base interface for LLM providers used in the fallback chain.

    ``check`` returns the frozen ``InferenceResult`` (contract) and must honour
    the per-call timeout. Providers raise on any failure (network, timeout,
    invalid model output) so the service can fail over and trip its breaker.
    """

    provider_id = "provider"

    @abstractmethod
    def check(self, prompt: str, timeout: float | None = None) -> InferenceResult:
        """Send a prompt to the model and return a validated InferenceResult."""

    @abstractmethod
    def is_available(self) -> bool:
        """Return True when the provider is reachable and healthy."""
