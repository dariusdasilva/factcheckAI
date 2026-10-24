import time

import requests

from apps.inference.output import SYSTEM_PROMPT, parse_model_output
from apps.inference.providers.base import BaseLLMProvider
from apps.inference.types import PROVIDER_REMOTE_API, InferenceResult


class RemoteLLMProvider(BaseLLMProvider):
    """OpenRouter-compatible remote provider (primary tier)."""

    provider_id = PROVIDER_REMOTE_API

    def __init__(
        self,
        api_key: str,
        model_id: str = "google/gemma-4-26b-a4b-it:free",
        *,
        input_price_per_mtok: float | None = None,
        output_price_per_mtok: float | None = None,
        timeout: float = 60,
    ):
        self.api_key = api_key
        self.model_id = model_id
        is_free_model = model_id.lower().endswith(":free")
        self.input_price_per_mtok = (
            0.0 if is_free_model and input_price_per_mtok is None else input_price_per_mtok
        )
        self.output_price_per_mtok = (
            0.0 if is_free_model and output_price_per_mtok is None else output_price_per_mtok
        )
        self.timeout = timeout
        self.endpoint = "https://openrouter.ai/api/v1/chat/completions"
        self.last_usage: tuple[int | None, int | None] = (None, None)

    def check(self, prompt: str, timeout: float | None = None) -> InferenceResult:
        start_time = time.time()
        request_timeout = min(timeout, self.timeout) if timeout is not None else self.timeout
        if request_timeout <= 0:
            raise TimeoutError("Remote inference deadline has expired")
        try:
            response = requests.post(
                self.endpoint,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "HTTP-Referer": "https://factcheckai.local",
                    "X-Title": "FactCheckAI",
                },
                json={
                    "model": self.model_id,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.3,
                    "top_p": 0.9,
                    "seed": 42,
                    "max_tokens": 512,
                    "response_format": {"type": "json_object"},
                },
                timeout=request_timeout,
            )
            response.raise_for_status()
            data = response.json()

            raw_output = data["choices"][0]["message"]["content"]
            latency_ms = int((time.time() - start_time) * 1000)
            usage = data.get("usage") or {}
            self.last_usage = (usage.get("prompt_tokens"), usage.get("completion_tokens"))
            return parse_model_output(
                raw_output,
                prompt,
                provider_used=self.provider_id,
                latency_ms=latency_ms,
            )
        except Exception as e:
            raise RuntimeError(f"RemoteLLMProvider error: {e}") from e

    def is_available(self) -> bool:
        try:
            response = requests.get("https://openrouter.ai/api/v1/models", timeout=5)
            return response.status_code == 200
        except Exception:
            return False
