"""Serializer for POST /api/v1/sources/ — extension pushes captured page text
into the crawl cache (§3 hop-2 is fed by the same Source table)."""

from rest_framework import serializers

MAX_SOURCE_TEXT_CHARS = 1_000_000  # §3.2: 1 MB source cap


class SourcePushSerializer(serializers.Serializer):
    url = serializers.URLField(max_length=2048)
    text = serializers.CharField()

    def validate_text(self, value: str) -> str:
        if len(value) > MAX_SOURCE_TEXT_CHARS:
            raise serializers.ValidationError(
                "Source text exceeds the 1 MB cap (§3.2)."
            )
        return value
