"""Cost estimation and a cache-backed, month-scoped spend counter."""

import hashlib
import math
import threading
import time
from datetime import datetime, timezone


class CostEstimator:
    """Estimate costs using prices expressed in USD per million tokens."""

    CHARS_PER_TOKEN = 4
    DEFAULT_OUTPUT_TOKENS = 512

    @staticmethod
    def _validate_price(price: float) -> float:
        price = float(price)
        if not math.isfinite(price) or price < 0:
            raise ValueError("Token prices must be finite, non-negative USD/MTok values")
        return price

    def estimate_cost(
        self,
        text: str,
        input_price_per_mtok: float,
        output_price_per_mtok: float,
        output_tokens: int = DEFAULT_OUTPUT_TOKENS,
    ) -> float:
        input_tokens = math.ceil(len(text) / self.CHARS_PER_TOKEN)
        return self.cost_for_tokens(
            input_tokens,
            output_tokens,
            input_price_per_mtok,
            output_price_per_mtok,
        )

    def cost_for_tokens(
        self,
        input_tokens: int,
        output_tokens: int,
        input_price_per_mtok: float,
        output_price_per_mtok: float,
    ) -> float:
        if input_tokens < 0 or output_tokens < 0:
            raise ValueError("Token counts cannot be negative")
        input_price = self._validate_price(input_price_per_mtok)
        output_price = self._validate_price(output_price_per_mtok)
        return (
            input_tokens * input_price + output_tokens * output_price
        ) / 1_000_000


class SpendManager:
    """Track estimated spend for a user and calendar month.

    Django's configured cache is used when available (Redis supports sharing
    across workers). Standalone use before Django settings are configured gets
    an isolated in-memory counter, suitable for tests and local experiments.
    Pass ``cache_backend`` to inject a cache explicitly.
    """

    NANO_DOLLARS_PER_DOLLAR = 1_000_000_000

    def __init__(self, monthly_cap: float = 5.0, *, cache_backend=None):
        if not math.isfinite(monthly_cap) or monthly_cap < 0:
            raise ValueError("Monthly spend cap must be finite and non-negative")
        self.monthly_cap = float(monthly_cap)
        self.cache_backend = cache_backend
        self._memory_spend: dict[str, int] = {}
        self._lock = threading.RLock()

    @property
    def current_spend(self) -> float:
        return self.get_spend("default")

    @current_spend.setter
    def current_spend(self, amount: float) -> None:
        key, _ = self._keys("default")
        units = self._to_units(amount)
        with self._locked(key):
            self._write(key, units, self._month_ttl())

    @classmethod
    def _to_units(cls, amount: float) -> int:
        amount = float(amount)
        if not math.isfinite(amount) or amount < 0:
            raise ValueError("Spend amount must be finite and non-negative")
        return math.ceil(amount * cls.NANO_DOLLARS_PER_DOLLAR)

    @staticmethod
    def _month_ttl() -> int:
        now = datetime.now(timezone.utc)
        if now.month == 12:
            next_month = datetime(now.year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            next_month = datetime(now.year, now.month + 1, 1, tzinfo=timezone.utc)
        return max(1, int((next_month - now).total_seconds()))

    def _keys(self, scope: str) -> tuple[str, str]:
        if not isinstance(scope, (str, int)) or not str(scope):
            raise ValueError("Spend scope must identify a user or account")
        now = datetime.now(timezone.utc)
        namespace = hashlib.sha256(str(scope).encode()).hexdigest()
        month = f"{now.year:04d}-{now.month:02d}"
        base = f"factchecker:inference:spend:{namespace}:{month}"
        return base, f"{base}:lock"

    def _backend(self):
        if self.cache_backend is not None:
            return self.cache_backend
        try:
            from django.conf import settings
            from django.core.cache import cache

            if settings.configured:
                return cache
        except ImportError:
            pass
        return None

    class _CacheLock:
        def __init__(self, manager, key):
            self.manager = manager
            self.key = key
            self.backend = manager._backend()
            self.token = f"{time.monotonic_ns()}-{threading.get_ident()}"

        def __enter__(self):
            if self.backend is None:
                self.manager._lock.acquire()
                return self
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                if self.backend.add(self.key, self.token, timeout=10):
                    return self
                time.sleep(0.01)
            raise TimeoutError("Could not acquire spend-ledger lock")

        def __exit__(self, *_exc):
            if self.backend is None:
                self.manager._lock.release()
            elif self.backend.get(self.key) == self.token:
                self.backend.delete(self.key)

    def _locked(self, key: str):
        return self._CacheLock(self, f"{key}:lock")

    def _read(self, key: str) -> int:
        backend = self._backend()
        if backend is None:
            return self._memory_spend.get(key, 0)
        return int(backend.get(key, 0))

    def _write(self, key: str, value: int, ttl: int) -> None:
        backend = self._backend()
        if backend is None:
            self._memory_spend[key] = value
        else:
            backend.set(key, value, timeout=ttl)

    def get_spend(self, scope: str = "default") -> float:
        key, _ = self._keys(scope)
        with self._locked(key):
            return self._read(key) / self.NANO_DOLLARS_PER_DOLLAR

    def reserve(
        self,
        estimated_cost: float,
        scope: str = "default",
        *,
        monthly_cap: float | None = None,
    ) -> bool:
        """Atomically reserve estimated spend before making a remote request."""
        units = self._to_units(estimated_cost)
        key, _ = self._keys(scope)
        cap = self.monthly_cap if monthly_cap is None else float(monthly_cap)
        if not math.isfinite(cap) or cap < 0:
            raise ValueError("Monthly spend cap must be finite and non-negative")
        cap_units = self._to_units(cap)
        with self._locked(key):
            current = self._read(key)
            if current + units > cap_units:
                return False
            self._write(key, current + units, self._month_ttl())
            return True

    def adjust_spend(self, delta: float, scope: str = "default") -> None:
        """Settle an estimate against actual usage, or release a failed call."""
        delta = float(delta)
        if not math.isfinite(delta):
            raise ValueError("Spend adjustment must be finite")
        key, _ = self._keys(scope)
        units = round(delta * self.NANO_DOLLARS_PER_DOLLAR)
        with self._locked(key):
            updated = max(0, self._read(key) + units)
            self._write(key, updated, self._month_ttl())

    def can_afford(self, estimated_cost: float, scope: str = "default") -> bool:
        units = self._to_units(estimated_cost)
        return self.get_spend(scope) + units / self.NANO_DOLLARS_PER_DOLLAR <= self.monthly_cap

    def add_spend(self, actual_cost: float, scope: str = "default") -> None:
        self.adjust_spend(actual_cost, scope)

    def get_spend_percentage(self, scope: str = "default") -> float:
        if self.monthly_cap == 0:
            return 100.0 if self.get_spend(scope) > 0 else 0.0
        return self.get_spend(scope) / self.monthly_cap * 100
