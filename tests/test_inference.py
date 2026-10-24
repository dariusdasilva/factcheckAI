import threading
import time
from unittest.mock import Mock, patch

import pytest

from apps.inference.catalog import ModelCatalog
from apps.inference.output import parse_model_output
from apps.inference.providers.base import BaseLLMProvider
from apps.inference.providers.gemini import GoogleGeminiProvider
from apps.inference.providers.ollama import OllamaProvider
from apps.inference.providers.remote_api import RemoteLLMProvider
from apps.inference.service import CircuitBreaker, InferenceService
from apps.inference.spend import CostEstimator, SpendManager
from apps.inference.types import FAIL_STATE, FALLBACK, OK, InferenceResult


class FakeCache:
    def __init__(self):
        self.values = {}
        self.lock = threading.Lock()

    def get(self, key, default=None):
        with self.lock:
            return self.values.get(key, default)

    def set(self, key, value, timeout=None):
        with self.lock:
            self.values[key] = value

    def add(self, key, value, timeout=None):
        with self.lock:
            if key in self.values:
                return False
            self.values[key] = value
            return True

    def delete(self, key):
        with self.lock:
            self.values.pop(key, None)


def inference_result(verdict="true", provider="remote_api"):
    return InferenceResult(
        verdict=verdict,
        confidence=0.8,
        evidence=[{"id": "W1", "hop": "wiki"}] if verdict != "unverified" else [],
        raw_model_output='{"verdict":"true","confidence":0.8,"evidence":["W1"]}',
        provider_used=provider,
        latency_ms=1,
        status=OK,
    )


def test_model_output_is_parsed_and_evidence_is_validated():
    result = parse_model_output(
        '{"verdict":"false","confidence":0.7,"evidence":["W1"]}',
        "Claim under review. Evidence: [W1]",
        provider_used="remote_api",
        latency_ms=10,
    )
    assert result.verdict == "false"
    assert result.evidence == [{"id": "W1", "hop": "wiki"}]
    assert result.status == OK

    with pytest.raises(ValueError):
        parse_model_output(
            '{"verdict":"true","confidence":0.9,"evidence":["W99"]}',
            "Claim under review. Evidence: [W1]",
            provider_used="remote_api",
            latency_ms=10,
        )
    with pytest.raises(ValueError):
        parse_model_output(
            '{"verdict":"true","confidence":0.9,"evidence":[]}',
            "Claim without evidence",
            provider_used="remote_api",
            latency_ms=10,
        )


def test_remote_provider_parses_real_response_and_passes_timeout():
    response = Mock()
    response.json.return_value = {
        "choices": [{
            "message": {
                "content": '{"verdict":"true","confidence":0.9,"evidence":["W1"]}'
            }
        }],
        "usage": {"prompt_tokens": 20, "completion_tokens": 12},
    }
    response.raise_for_status.return_value = None
    provider = RemoteLLMProvider("test-key", input_price_per_mtok=1.0, output_price_per_mtok=2.0)

    with patch("apps.inference.providers.remote_api.requests.post", return_value=response) as post:
        result = provider.check("Claim. Evidence: [W1]", timeout=4.5)

    assert result.verdict == "true"
    assert result.evidence == [{"id": "W1", "hop": "wiki"}]
    assert result.provider_used == "remote_api"
    assert provider.last_usage == (20, 12)
    assert post.call_args.kwargs["timeout"] == 4.5
    assert post.call_args.kwargs["json"]["max_tokens"] == 512


def test_ollama_provider_parses_response_and_keeps_context_options():
    response = Mock()
    response.json.return_value = {
        "message": {
            "content": '{"verdict":"unverified","confidence":0.2,"evidence":[]}'
        },
        "prompt_eval_count": 30,
        "eval_count": 10,
    }
    response.raise_for_status.return_value = None
    provider = OllamaProvider()

    with patch("apps.inference.providers.ollama.requests.post", return_value=response) as post:
        result = provider.check("Claim. No evidence.", timeout=3)

    assert result.verdict == "unverified"
    assert result.evidence == []
    assert provider.last_usage == (30, 10)
    assert post.call_args.kwargs["timeout"] == 3
    assert post.call_args.kwargs["json"]["options"]["num_ctx"] == 8192


class FakeProvider(BaseLLMProvider):
    provider_id = "remote_api"
    input_price_per_mtok = 1.0
    output_price_per_mtok = 1.0

    def __init__(self, result=None, error=None, delay=0):
        self.result = result
        self.error = error
        self.delay = delay
        self.received_timeout = None
        self.calls = 0
        self.last_usage = (None, None)

    def check(self, prompt, timeout=None):
        self.calls += 1
        self.received_timeout = timeout
        if self.delay:
            time.sleep(self.delay)
        if self.error:
            raise self.error
        return self.result

    def is_available(self):
        return True


class LocalProvider(FakeProvider):
    provider_id = "ollama"


def test_service_falls_back_to_local_after_remote_error():
    remote = FakeProvider(error=RuntimeError("remote unavailable"))
    local = LocalProvider(result=inference_result(provider="ollama"))
    service = InferenceService([remote, local], total_timeout_seconds=1)

    outcome = service.check("Claim. Evidence: [W1]")
    result = outcome.result

    assert result.status == FALLBACK
    assert result.provider_used == "ollama"
    assert result.verdict == "true"
    assert remote.received_timeout is not None
    assert outcome.providers_tried == ["remote_api", "ollama"]


def test_both_providers_fail_with_explicit_fail_state():
    service = InferenceService([
        FakeProvider(error=RuntimeError("remote down")),
        LocalProvider(error=RuntimeError("local down")),
    ])

    outcome = service.check("A claim")

    assert outcome.result.status == FAIL_STATE
    assert outcome.result.verdict is None
    assert outcome.result.evidence == []
    assert outcome.providers_tried == ["remote_api", "ollama"]
    assert outcome.retry_after == 60


def test_spend_cap_skips_remote_and_uses_local_provider():
    remote = FakeProvider(result=inference_result())
    local = LocalProvider(result=inference_result(provider="ollama"))
    service = InferenceService(
        [remote, local],
        spend_manager=SpendManager(monthly_cap=0),
    )

    outcome = service.check("Claim with non-zero input cost")

    assert outcome.result.status == FALLBACK
    assert remote.calls == 0
    assert local.calls == 1


def test_remote_success_returns_price_and_usage_snapshot():
    provider = FakeProvider(result=inference_result())
    provider.last_usage = (100, 50)
    manager = SpendManager(monthly_cap=1)
    service = InferenceService([provider], spend_manager=manager)

    outcome = service.check("Claim with evidence [W1]")

    assert outcome.result.status == OK
    assert outcome.price_in_per_mtok == 1.0
    assert outcome.price_out_per_mtok == 1.0
    assert outcome.tokens_in == 100
    assert outcome.tokens_out == 50
    assert outcome.cost_usd == pytest.approx(0.00015)
    assert manager.current_spend == pytest.approx(outcome.cost_usd)


def test_service_enforces_wall_clock_deadline():
    provider = FakeProvider(result=inference_result(), delay=0.2)
    service = InferenceService([provider], total_timeout_seconds=0.03)

    started = time.monotonic()
    outcome = service.check("A claim")
    elapsed = time.monotonic() - started

    assert outcome.result.status == FAIL_STATE
    assert outcome.result.verdict is None
    assert elapsed < 0.15
    assert provider.received_timeout <= 0.05


def test_circuit_breaker_allows_only_one_half_open_probe():
    breaker = CircuitBreaker(failure_threshold=1, cooldown_period=10)
    with patch("apps.inference.service.time.monotonic", return_value=100):
        breaker.record_failure("remote_api")
    with patch("apps.inference.service.time.monotonic", return_value=111):
        assert breaker.is_available("remote_api")
        assert not breaker.is_available("remote_api")
        breaker.record_success("remote_api")
        assert breaker.is_available("remote_api")


def test_spend_manager_is_month_scoped_and_shared_by_cache_backend():
    cache = FakeCache()
    first = SpendManager(monthly_cap=1, cache_backend=cache)
    second = SpendManager(monthly_cap=1, cache_backend=cache)

    assert first.reserve(0.75, scope="user-42")
    assert not second.reserve(0.30, scope="user-42")
    second.adjust_spend(-0.25, scope="user-42")
    assert second.get_spend("user-42") == pytest.approx(0.5)
    assert second.reserve(0.30, scope="user-42")
    assert second.get_spend("other-user") == 0


def test_cost_estimator_uses_per_million_token_units():
    estimator = CostEstimator()
    assert estimator.cost_for_tokens(1_000_000, 0, 2.0, 0.0) == 2.0
    assert estimator.estimate_cost("1234", 1.0, 2.0, output_tokens=512) == pytest.approx(
        0.001025
    )


def test_remote_catalog_converts_openrouter_per_token_prices_and_caches():
    cache = FakeCache()
    catalog = ModelCatalog(remote_endpoint="https://catalog.test/models", cache_backend=cache)
    response = Mock()
    response.json.return_value = {
        "data": [{
            "id": "google/gemma-test",
            "context_length": 8192,
            "pricing": {"prompt": "0.0000002", "completion": "0.0000004"},
        }]
    }
    response.raise_for_status.return_value = None

    with patch("apps.inference.catalog.requests.get", return_value=response) as get:
        first = catalog.get_remote_models()
        second = catalog.get_remote_models()

    assert first[0].input_price_per_mtok == pytest.approx(0.2)
    assert first[0].output_price_per_mtok == pytest.approx(0.4)
    assert second == first
    get.assert_called_once()


def test_empty_provider_list_returns_fail_state_not_exception():
    outcome = InferenceService([]).check("Claim")
    assert outcome.result.status == FAIL_STATE
    assert outcome.result.verdict is None


def test_gemini_provider_uses_native_generatecontent_and_parses():
    response = Mock()
    response.json.return_value = {
        "candidates": [{
            "content": {
                "parts": [{
                    "text": '```json\n{"verdict":"true","confidence":0.9,"evidence":["W1"]}\n```'
                }]
            }
        }],
        "usageMetadata": {"promptTokenCount": 20, "candidatesTokenCount": 12},
    }
    response.raise_for_status.return_value = None
    provider = GoogleGeminiProvider("test-google-key")

    with patch("apps.inference.providers.gemini.requests.post", return_value=response) as post:
        result = provider.check("Claim. Evidence: [W1]", timeout=5)

    assert result.verdict == "true"
    assert result.evidence == [{"id": "W1", "hop": "wiki"}]
    assert provider.last_usage == (20, 12)
    assert provider.provider_id == "remote_api"

    url = post.call_args.args[0]
    assert ":generateContent" in url
    assert "gemma-4-26b-a4b-it" in url
    body = post.call_args.kwargs["json"]
    assert body["generationConfig"]["responseMimeType"] == "application/json"
    assert "systemInstruction" in body
