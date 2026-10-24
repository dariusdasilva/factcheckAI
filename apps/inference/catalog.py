import logging
import math
import threading
import time

import requests

from apps.inference.types import ModelInfo

logger = logging.getLogger(__name__)

class ModelCatalog:
    """
    Fetches and filters models from OpenRouter and Ollama.
    Implements B3 from WORK_CHUNKS.md.
    """

    CACHE_TTL_SECONDS = 24 * 60 * 60
    _memory_cache: dict[str, tuple[float, list[ModelInfo]]] = {}
    _cache_lock = threading.Lock()

    def __init__(
        self,
        remote_endpoint: str = "https://openrouter.ai/api/v1/models",
        local_endpoint: str = "http://localhost:11434/api/tags",
        *,
        cache_backend=None,
    ):
        self.remote_endpoint = remote_endpoint
        self.local_endpoint = local_endpoint
        self.cache_backend = cache_backend

    def _cache_get(self, key: str) -> list[ModelInfo] | None:
        if self.cache_backend is not None:
            return self.cache_backend.get(key)
        try:
            from django.core.cache import cache

            return cache.get(key)
        except Exception:
            with self._cache_lock:
                entry = self._memory_cache.get(key)
                if entry and entry[0] > time.monotonic():
                    return entry[1]
                self._memory_cache.pop(key, None)
                return None

    def _cache_set(self, key: str, value: list[ModelInfo]) -> None:
        if self.cache_backend is not None:
            self.cache_backend.set(key, value, self.CACHE_TTL_SECONDS)
            return
        try:
            from django.core.cache import cache

            cache.set(key, value, self.CACHE_TTL_SECONDS)
        except Exception:
            with self._cache_lock:
                self._memory_cache[key] = (
                    time.monotonic() + self.CACHE_TTL_SECONDS,
                    value,
                )

    @staticmethod
    def _openrouter_price_per_mtok(raw_price) -> float:
        """OpenRouter catalog prices are USD/token; expose USD per million tokens."""
        price = float(raw_price)
        if not math.isfinite(price) or price < 0:
            raise ValueError("OpenRouter returned an invalid token price")
        return price * 1_000_000

    def get_remote_models(self) -> list[ModelInfo]:
        """
        Fetch OpenRouter models, filter for Gemma family, and return as ModelInfo.
        """
        cache_key = f"inference:catalog:openrouter:{self.remote_endpoint}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        try:
            response = requests.get(self.remote_endpoint, timeout=10)
            response.raise_for_status()
            data = response.json().get("data", [])

            gemma_models = []
            for m in data:
                model_id = m.get("id", "")
                # Filter for Gemma family
                if "gemma" in model_id.lower():
                    # OpenRouter provides pricing in a specific format, we normalize to per 1M tokens
                    # Note: Pricing fields may vary, we use defaults if missing
                    pricing = m.get("pricing", {})

                    # Legacy filter: Gemma 2 27b has 8k context
                    is_legacy = "gemma-2-27b" in model_id.lower()

                    is_free = model_id.lower().endswith(":free")
                    try:
                        if is_free:
                            input_price = output_price = 0.0
                        else:
                            input_price = self._openrouter_price_per_mtok(pricing["prompt"])
                            output_price = self._openrouter_price_per_mtok(pricing["completion"])
                        gemma_models.append(ModelInfo(
                            model_id=model_id,
                            context_window=int(m.get("context_length", 0)),
                            input_price_per_mtok=input_price,
                            output_price_per_mtok=output_price,
                            is_free=is_free,
                            is_local=False,
                            is_legacy=is_legacy
                        ))
                    except (KeyError, TypeError, ValueError) as error:
                        logger.warning("Skipping model %s with invalid pricing: %s", model_id, error)
            self._cache_set(cache_key, gemma_models)
            return gemma_models
        except Exception as e:
            logger.error(f"Error fetching remote models: {e}")
            return []

    def get_local_models(self) -> list[ModelInfo]:
        """
        Fetch installed models from local Ollama instance.
        """
        try:
            response = requests.get(self.local_endpoint, timeout=5)
            response.raise_for_status()
            data = response.json().get("models", [])

            local_models = []
            for m in data:
                name = m.get("name", "")
                # Only show Gemma models locally
                if "gemma" in name.lower():
                    local_models.append(ModelInfo(
                        model_id=name,
                        context_window=0,
                        input_price_per_mtok=0.0,
                        output_price_per_mtok=0.0,
                        is_free=True,
                        is_local=True,
                        is_legacy=False
                    ))
            return local_models
        except Exception as e:
            logger.error(f"Error fetching local models: {e}")
            return []
