"""A3 tests: settings/model upsert + spend/models stubs. Hermetic."""

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import ModelSetting

pytestmark = [pytest.mark.django_db]

FREE_MODEL = "google/gemma-4-26b-a4b-it:free"
LOCAL_MODEL = "gemma4:e4b-it-qat"


@pytest.fixture()
def client_fixture(django_user_model):
    user = django_user_model.objects.create_user(username="settingsuser", password="x")
    client = APIClient()
    client.force_authenticate(user=user)
    return client, user


def test_put_then_get_settings_roundtrip(client_fixture):
    client, user = client_fixture

    put_api = client.put(
        "/api/v1/settings/model/",
        {"tier": "api", "model_id": FREE_MODEL, "spend_cap_monthly": "5.00"},
        format="json",
    )
    assert put_api.status_code == 200

    put_local = client.put(
        "/api/v1/settings/model/",
        {"tier": "local", "model_id": LOCAL_MODEL},
        format="json",
    )
    assert put_local.status_code == 200

    rows = ModelSetting.objects.filter(user=user)
    assert rows.count() == 2
    by_tier = {row.tier: row for row in rows}
    assert by_tier[ModelSetting.Tier.API].model_id == FREE_MODEL
    assert str(by_tier[ModelSetting.Tier.API].spend_cap_monthly) == "5.00"

    fetched = client.get("/api/v1/settings/model/").json()
    assert sorted(s["tier"] for s in fetched["settings"]) == ["api", "local"]


def test_put_updates_existing_row_without_duplicating(client_fixture):
    client, user = client_fixture
    payload = {"tier": "api", "model_id": FREE_MODEL}
    client.put("/api/v1/settings/model/", payload, format="json")
    client.put(
        "/api/v1/settings/model/",
        {"tier": "api", "model_id": "google/gemma-3-12b-it"},
        format="json",
    )
    assert ModelSetting.objects.filter(user=user).count() == 1
    assert ModelSetting.objects.get(user=user).model_id == "google/gemma-3-12b-it"


def test_put_rejects_spend_cap_on_local_tier(client_fixture):
    client, _ = client_fixture
    response = client.put(
        "/api/v1/settings/model/",
        {"tier": "local", "model_id": LOCAL_MODEL, "spend_cap_monthly": "5.00"},
        format="json",
    )
    assert response.status_code == 400
    assert "spend_cap_monthly" in response.json()


def test_put_rejects_unknown_tier(client_fixture):
    client, _ = client_fixture
    response = client.put(
        "/api/v1/settings/model/",
        {"tier": "quantum", "model_id": LOCAL_MODEL},
        format="json",
    )
    assert response.status_code == 400


def test_spend_stub_shape(client_fixture):
    client, _ = client_fixture
    data = client.get("/api/v1/spend/").json()
    assert {"month_to_date_usd", "by_provider", "avg_cost_per_check_usd"} <= set(data)
    assert data["month_to_date_usd"] is None  # B4 fills the ledger maths


def test_models_stub_shape_and_flags_stub(client_fixture):
    client, _ = client_fixture
    data = client.get("/api/v1/models/").json()
    assert data["stub"] is True  # B3 replaces this with the live catalog
    assert len(data["api_models"]) > 0
    assert data["local_models"] == []
