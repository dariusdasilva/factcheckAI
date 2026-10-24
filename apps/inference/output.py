"""Strict parsing and validation for model verdicts (AGENTS.md §4.2, §4.5)."""

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from apps.inference.types import OK, InferenceResult

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


def evidence_id_to_item(evidence_id: str) -> dict[str, str]:
    """Map a cited ``W#``/``S#`` label to the ``Evidence``-shaped dict."""
    hop = "wiki" if evidence_id.startswith("W") else "cited_source"
    return {"id": evidence_id, "hop": hop}


def parse_model_output(
    raw_output: str,
    prompt: str,
    *,
    provider_used: str,
    latency_ms: int,
) -> InferenceResult:
    """Parse a model response into the frozen ``InferenceResult``.

    Rejects (raises ``ValueError``) any output the model halves the fail-state
    law: malformed JSON, an illegal verdict, a confidence out of range, or a
    citation to an evidence id that was never supplied (§4.5).
    """
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
        evidence=[evidence_id_to_item(eid) for eid in parsed.evidence],
        raw_model_output=raw_output,
        provider_used=provider_used,
        latency_ms=latency_ms,
        status=OK,
    )
