"""Settings sanity — Django configures with the repo's split settings.

Replaces the pre-scaffold placeholder (see its original comment). Hermetic:
no network, no fixtures beyond stock Django.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from django.conf import settings

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_dev_settings_load():
    assert settings.INSTALLED_APPS, "INSTALLED_APPS must be populated"


@pytest.mark.django_db
def test_database_connection_works():
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        assert cursor.fetchone()[0] == 1


def _setup_prod_settings(secret_key: str | None) -> subprocess.CompletedProcess:
    """Import prod settings in a clean interpreter with DJANGO_SECRET_KEY unset."""
    env = {k: v for k, v in os.environ.items() if k != "DJANGO_SECRET_KEY"}
    env["DJANGO_SETTINGS_MODULE"] = "config.settings.prod"
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    if secret_key is not None:
        env["DJANGO_SECRET_KEY"] = secret_key
    return subprocess.run(
        [
            sys.executable,
            "-c",
            "import django; django.setup(); "
            "from django.conf import settings; "
            "print(settings.DEBUG, settings.SECRET_KEY)",
        ],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_prod_settings_refuse_to_start_without_a_secret_key():
    # Audit #2 finding: prod silently inherited base.py's insecure dev key.
    if (PROJECT_ROOT / ".env").exists():
        pytest.skip("a local .env would satisfy DJANGO_SECRET_KEY")

    result = _setup_prod_settings(secret_key=None)

    assert result.returncode != 0
    assert "DJANGO_SECRET_KEY" in result.stderr


def test_prod_settings_start_with_a_secret_key_and_force_debug_off():
    result = _setup_prod_settings(secret_key="test-only-secret")

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "False test-only-secret"
