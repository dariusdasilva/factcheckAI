"""Strict parsing and validation for model verdicts."""

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from apps.inference.types import InferenceResult, InferenceStatus

EVIDENCE_ID_PATTERN = re.compile(r"\[(W\d+|S\d+)\]")


class ModelVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: Literal["true", "false", "unverified"]
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[str]


SYSTEM_PROMPT = """You are a fact-checking assistant. Judge only the given claim using only the supplied evidence ids. If evidence is insufficient, use verdict \"unverified\". Never invent evidence ids.

Return one JSON object matching this schema exactly:
{"verdict":"true|false|unverified","confidence":0.0,"evidence":["W1"]}

Example: {"verdict":"unverified","confidence":0.2,"evidence":[]}

The evidence array contains only ids present in the supplied evidence. Return \"unverified\" with an empty evidence array when no supplied evidence supports a verdict. Return JSON only."""


def parse_model_output(
    raw_output: str,
    prompt: str,
    *,
    provider_used: str,
    latency_ms: int,
    tokens_in: int | None = None,
    tokens_out: int | None = None,
    price_in_per_mtok: float | None = None,
    price_out_per_mtok: float | None = None,
) -> InferenceResult:
    """Parse the model response and reject malformed or out-of-bundle citations."""
    parsed = ModelVerdict.model_validate_json(raw_output, strict=True)
    allowed_ids = set(EVIDENCE_ID_PATTERN.findall(prompt))
    if parsed.verdict != "unverified" and not parsed.evidence:
        raise ValueError("A true/false verdict must cite at least one supplied evidence id")
    if any(evidence_id not in allowed_ids for evidence_id in parsed.evidence):
        raise ValueError("Model cited an evidence id not present in the supplied prompt")
    if any(re.fullmatch(r"(?:W|S)\d+", evidence_id) is None for evidence_id in parsed.evidence):
        raise ValueError("Model evidence must contain only supplied W#/S# ids")

    return InferenceResult(
        verdict=parsed.verdict,
        confidence=parsed.confidence,
        evidence=parsed.evidence,
        raw_model_output=raw_output,
        provider_used=provider_used,
        latency_ms=latency_ms,
        status=InferenceStatus.OK,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        price_in_per_mtok=price_in_per_mtok,
        price_out_per_mtok=price_out_per_mtok,
    )
