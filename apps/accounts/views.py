"""User-scope REST views (A3): model settings and API key creation."""

import secrets

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.models import ApiKey, ModelSetting
from apps.accounts.serializers import ModelSettingSerializer, ModelSettingUpsertSerializer

API_KEY_PREFIX = "fcai_"
API_KEY_BYTES = 32  # token_urlsafe output ≈ 43 urlsafe chars for 32 bytes


@api_view(["PUT", "GET"])
def model_settings(request: Request) -> Response:
    """PUT /api/v1/settings/model/ — upsert one tier's default model (§3).

    GET returns the same shape so the settings UIs (D5) can read current
    values; flagged as a contract addition for the wk-2 freeze sign-off.
    """
    if request.method == "PUT":
        in_serializer = ModelSettingUpsertSerializer(data=request.data)
        in_serializer.is_valid(raise_exception=True)
        data = in_serializer.validated_data
        defaults = {"model_id": data["model_id"]}
        # Only touch the spend cap when the caller actually sent it — omitting
        # the field must not silently wipe a configured cap (audit finding A6).
        if "spend_cap_monthly" in data:
            defaults["spend_cap_monthly"] = data["spend_cap_monthly"]
        ModelSetting.objects.update_or_create(
            user=request.user,
            tier=data["tier"],
            defaults=defaults,
        )

    rows = ModelSetting.objects.filter(user=request.user)
    out_serializer = ModelSettingSerializer(rows, many=True)
    return Response({"settings": out_serializer.data})


@api_view(["POST"])
def create_api_key(request: Request) -> Response:
    """POST /api/v1/auth/keys/ — create an extension bearer key (§3, §6).

    The raw key is shown exactly once; only its SHA-256 hash is stored.
    """
    raw_key = f"{API_KEY_PREFIX}{secrets.token_urlsafe(API_KEY_BYTES)}"
    key = request.user.api_keys.create(key_hash=ApiKey.hash_key(raw_key))

    return Response(
        {
            "id": key.pk,
            "key": raw_key,
            "created_at": key.created_at.isoformat(),
            "note": "Copy this key now — it is shown only once (only a SHA-256 hash is stored).",
        },
        status=status.HTTP_201_CREATED,
    )
