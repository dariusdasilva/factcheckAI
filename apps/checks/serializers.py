"""Serializers for the checks API (deliverable A3).

Request/response shapes here are the frozen A→D contract (ARCHITECTURE.md §3).
Prompt size caps apply at the door per §6 (prompt-injection hygiene): the claim
is capped in characters; scrubbing/limits live in B's template layer.
"""

from rest_framework import serializers

from apps.checks.models import CheckRun, CheckRunStatus, Evidence

MAX_CLAIM_CHARS = 4000


class ContextSerializer(serializers.Serializer):
    """Extension/web context accompanying a submitted claim (§3 example)."""

    source_url = serializers.URLField(
        required=False, help_text="Page the claim was captured from."
    )
    selection = serializers.BooleanField(
        required=False, help_text="True when the claim is a page selection."
    )


class SubmitCheckSerializer(serializers.Serializer):
    claim = serializers.CharField(max_length=MAX_CLAIM_CHARS)
    context = ContextSerializer(required=False)

    def validate_claim(self, value: str) -> str:
        stripped = value.strip()
        if len(stripped) < 3:
            raise serializers.ValidationError(
                "The claim must be at least 3 visible characters long."
            )
        return stripped


class EvidenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Evidence
        fields = ("id", "hop", "url", "title", "snippet", "relevance")


class CheckRunListSerializer(serializers.ModelSerializer):
    check_id = serializers.IntegerField(source="id", read_only=True)
    claim_text = serializers.CharField(source="claim.text", read_only=True)

    class Meta:
        model = CheckRun
        fields = (
            "check_id",
            "status",
            "claim_text",
            "verdict_enum",
            "confidence",
            "created_at",
        )


class CheckRunResultSerializer(serializers.ModelSerializer):
    """Poll body for GET /checks/{id}/ (§2.2).

    While queued/running, only progress fields are meaningful. Terminal runs
    carry the InferenceResult-equivalent fields; on fail_state the response
    additionally includes detail/retry_after/providers_tried per the §2.2
    envelope — those keys are stripped on non-fail-state runs.
    """

    check_id = serializers.IntegerField(source="id", read_only=True)
    claim_text = serializers.CharField(source="claim.text", read_only=True)
    evidence = EvidenceSerializer(many=True, read_only=True)
    detail = serializers.SerializerMethodField()
    retry_after = serializers.SerializerMethodField()
    providers_tried = serializers.SerializerMethodField()

    class Meta:
        model = CheckRun
        fields = (
            "check_id",
            "status",
            "claim_text",
            "verdict_enum",
            "confidence",
            "evidence",
            "provider_used",
            "model_id",
            "tokens_in",
            "tokens_out",
            "latency_ms",
            "detail",
            "retry_after",
            "providers_tried",
            "created_at",
            "finished_at",
        )

    def latest_fail_state_payload(self, run: CheckRun) -> dict:
        log = run.audit_logs.filter(event="fail_state_entered").first()
        if log and isinstance(log.json_payload, dict):
            return log.json_payload
        return {}

    def get_detail(self, run: CheckRun) -> str:
        from apps.checks.contracts import FAIL_STATE_DETAIL

        return self.latest_fail_state_payload(run).get("detail", FAIL_STATE_DETAIL)

    def get_retry_after(self, run: CheckRun) -> int:
        from apps.checks.contracts import DEFAULT_FAIL_RETRY_AFTER_S

        return self.latest_fail_state_payload(run).get(
            "retry_after", DEFAULT_FAIL_RETRY_AFTER_S
        )

    def get_providers_tried(self, run: CheckRun) -> list:
        from apps.checks.contracts import DEFAULT_PROVIDERS_TRIED

        payload = self.latest_fail_state_payload(run).get("providers_tried")
        if payload:
            return payload
        providers = [run.provider_used] if run.provider_used else []
        return list(providers) or list(DEFAULT_PROVIDERS_TRIED)

    def to_representation(self, run: CheckRun) -> dict:
        data = super().to_representation(run)
        if run.status != CheckRunStatus.FAIL_STATE:
            for key in ("detail", "retry_after", "providers_tried"):
                data.pop(key, None)
        return data
