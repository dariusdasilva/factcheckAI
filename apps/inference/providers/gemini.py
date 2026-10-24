import time

import requests

from apps.inference.output import SYSTEM_PROMPT, parse_model_output
from apps.inference.providers.base import BaseLLMProvider
from apps.inference.types import PROVIDER_REMOTE_API, InferenceResult


class GoogleGeminiProvider(BaseLLMProvider):
    """Google Gemini API remote provider (native ``generateContent``).

    The OpenAI-compatible Gemini endpoint does not serve the open Gemma models,
    so this provider talks to the native endpoint
    ``/v1beta/models/{model}:generateContent`` (ARCHITECTURE.md §2.2's documented
    "Google as an alternative remote tier"). Gemma 4 ids are bare, e.g.
    ``gemma-4-26b-a4b-it``.
    """

    provider_id = PROVIDER_REMOTE_API

    def __init__(
        self,
        api_key: str,
        model_id: str = "gemma-4-26b-a4b-it",
        *,
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
        timeout: float = 60,
    ):
        self.api_key = api_key
        self.model_id = model_id
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        # Gemma on the Gemini API is free tier, so prices stay zero for the ledger.
        self.input_price_per_mtok = 0.0
        self.output_price_per_mtok = 0.0
        self.last_usage: tuple[int | None, int | None] = (None, None)

    def check(self, prompt: str, timeout: float | None = None) -> InferenceResult:
        start_time = time.time()
        request_timeout = min(timeout, self.timeout) if timeout is not None else self.timeout
        if request_timeout <= 0:
            raise TimeoutError("GoogleGeminiProvider inference deadline has expired")
        try:
            response = requests.post(
                f"{self.base_url}/models/{self.model_id}:generateContent",
                headers={
                    "Content-Type": "application/json",
                    "x-goog-api-key": self.api_key,
                },
                json={
                    "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                    "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
                    "generationConfig": {
                        "temperature": 0.3,
                        "topP": 0.9,
                        "topK": 40,
                        "maxOutputTokens": 512,
                        "responseMimeType": "application/json",
                    },
                },
                timeout=request_timeout,
            )
            response.raise_for_status()
            data = response.json()

            raw_output = data["candidates"][0]["content"]["parts"][0]["text"]
            latency_ms = int((time.time() - start_time) * 1000)
            usage = data.get("usageMetadata") or {}
            self.last_usage = (
                usage.get("promptTokenCount"),
                usage.get("candidatesTokenCount"),
            )
            return parse_model_output(
                raw_output,
                prompt,
                provider_used=self.provider_id,
                latency_ms=latency_ms,
            )
        except Exception as e:
            raise RuntimeError(f"GoogleGeminiProvider error: {e}") from e

    def is_available(self) -> bool:
        try:
            response = requests.get(
                f"{self.base_url}/models/{self.model_id}",
                headers={"x-goog-api-key": self.api_key},
                timeout=5,
            )
            return response.status_code == 200
        except Exception:
            return False
