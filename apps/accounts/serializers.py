"""Serializers for user-scope endpoints (A3): model settings + API keys."""

from rest_framework import serializers

from apps.accounts.models import ModelSetting


class ModelSettingUpsertSerializer(serializers.Serializer):
    """PUT /settings/model/ body: {tier, model_id, spend_cap_monthly?}."""

    tier = serializers.ChoiceField(choices=ModelSetting.Tier.choices)
    model_id = serializers.CharField(max_length=255)
    spend_cap_monthly = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        allow_null=True,
        min_value=0,
    )

    def validate(self, attrs: dict) -> dict:
        if (
            attrs.get("tier") == ModelSetting.Tier.LOCAL
            and attrs.get("spend_cap_monthly") is not None
        ):
            raise serializers.ValidationError(
                {"spend_cap_monthly": "The spend cap applies only to the api tier (§3.1)."}
            )
        return attrs


class ModelSettingSerializer(serializers.ModelSerializer):
    class Meta:
        model = ModelSetting
        fields = ("tier", "model_id", "spend_cap_monthly", "updated_at")
