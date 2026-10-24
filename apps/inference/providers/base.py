from abc import ABC, abstractmethod
from apps.inference.types import InferenceResult

class BaseLLMProvider(ABC):
    """Base interface for LLM providers used in the fallback chain."""

    provider_id = "provider"

    @abstractmethod
    def check(self, prompt: str, timeout: float | None = None) -> InferenceResult:
        """
        Sends a prompt to the model and returns an InferenceResult.
        Implementations must honor the supplied per-call timeout.
        Should raise a specific exception on network/provider failure
        to trigger the circuit breaker.
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the provider is reachable and healthy."""
        pass
