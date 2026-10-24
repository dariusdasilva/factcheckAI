"""Shared pytest configuration for the test suite.

Cache isolation: pytest-django resets the database between tests (so user pks
restart at 1) while Django's cache survives the whole session. Without this
fixture, throttle history written by one test leaks into another's user — e.g.
a test's first authenticated request can inherit the previous test's 429.
"""

import pytest


@pytest.fixture(autouse=True)
def _isolated_cache():
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()
