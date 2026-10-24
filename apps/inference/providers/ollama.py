import time

import requests

from apps.inference.output import SYSTEM_PROMPT, ModelVerdict, parse_model_output
from apps.inference.providers.base import BaseLLMProvider
from apps.inference.types import PROVIDER_OLLAMA, InferenceResult


class OllamaProvider(BaseLLMProvider):
    """Local Ollama provider (secondary tier, §2.2)."""

    provider_id = PROVIDER_OLLAMA

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model_id: str = "gemma4:e4b-it-qat",
        *,
        timeout: float = 90,
    ):
        self.base_url = base_url
        self.model_id = model_id
        self.timeout = timeout
        self.last_usage: tuple[int | None, int | None] = (None, None)

    def check(self, prompt: str, timeout: float | None = None) -> InferenceResult:
        start_time = time.time()
        request_timeout = min(timeout, self.timeout) if timeout is not None else self.timeout
        if request_timeout <= 0:
            raise TimeoutError("Ollama inference deadline has expired")
        try:
            response = requests.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model_id,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "stream": False,
                    "format": ModelVerdict.model_json_schema(),
                    "keep_alive": "5m",
                    "options": {
                        "temperature": 0.3,
                        "top_p": 0.9,
                        "top_k": 40,
                        "seed": 42,
                        "num_ctx": 8192,
                        "num_predict": 512,
                    },
                },
                timeout=request_timeout,
            )
            response.raise_for_status()
            data = response.json()

            raw_output = data["message"]["content"]
            latency_ms = int((time.time() - start_time) * 1000)
            self.last_usage = (data.get("prompt_eval_count"), data.get("eval_count"))
            return parse_model_output(
                raw_output,
                prompt,
                provider_used=self.provider_id,
                latency_ms=latency_ms,
            )
        except Exception as e:
            raise RuntimeError(f"OllamaProvider error: {e}") from e

    def is_available(self) -> bool:
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            return response.status_code == 200
        except Exception:
            return False
