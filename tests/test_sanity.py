"""Settings sanity — Django configures with the repo's split settings.

Replaces the pre-scaffold placeholder (see its original comment). Hermetic:
no network, no fixtures beyond stock Django.
"""

import pytest
from django.conf import settings


def test_dev_settings_load():
    assert settings.INSTALLED_APPS, "INSTALLED_APPS must be populated"


@pytest.mark.django_db
def test_database_connection_works():
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        assert cursor.fetchone()[0] == 1
