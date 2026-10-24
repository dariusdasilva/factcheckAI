"""C6 — Evidence packer: rank snippets into a labelled bundle inside a token budget.

ARCHITECTURE.md §3.2 stage 5. All hop-1 (``W*``) and hop-2 (``S*``) snippets are
ranked against the claim with BM25 keyword overlap — **no extra model call** — then
filled into a token budget (default 6k). The result is the exact, enumerated set of
evidence ids the prompt may cite: the pydantic layer downstream rejects any citation
to an id not in :meth:`EvidenceBundle.labels` (AGENTS.md §4.5), which is how the
"model invented a source" failure mode is caught.

Token counts use the ``chars / 4`` estimate from §3.1 rather than a tokenizer
download, so the packer stays hermetic and consistent with the spend maths.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from rank_bm25 import BM25Okapi

from .article_read import WikiEvidence
from .constants import DEFAULT_TOKEN_BUDGET
from .discovery import tokenize
from .source_fetch import SourceEvidence

_HOP_ORDER = {"wiki": 0, "cited_source": 1}


def estimate_tokens(text: str) -> int:
    """§3.1: ``est_tokens ≈ chars / 4``. Hermetic — no tokenizer download."""
    return max(1, len(text) // 4)


def _truncate_to_tokens(text: str, token_budget: int) -> str:
    return text[: max(0, token_budget * 4)].rstrip()


def _bm25_scores(claim: str, snippets: list[str]) -> list[float]:
    """BM25 keyword overlap, plus a plain-overlap term.

    BM25's idf is 0 for terms appearing in exactly half a two-document corpus, so
    on tiny bundles it cannot discriminate. Adding the fraction of the claim's
    keywords a snippet contains keeps ranking meaningful even with two snippets.
    """
    query_tokens = set(tokenize(claim))
    query_token_count = max(1, len(query_tokens))
    overlaps = [
        len(query_tokens & set(tokenize(snippet))) / query_token_count
        for snippet in snippets
    ]
    corpus = [tokenize(snippet) for snippet in snippets]
    if any(corpus):
        bm25 = BM25Okapi(corpus)
        bm25_scores = [float(score) for score in bm25.get_scores(tokenize(claim))]
    else:
        bm25_scores = [0.0] * len(snippets)
    return [
        bm25_score + overlap
        for bm25_score, overlap in zip(bm25_scores, overlaps, strict=True)
    ]


@dataclass(frozen=True)
class PackedEvidence:
    """One labelled snippet in the bundle, ready to render as ``[W#]``/``[S#]``."""

    label: str
    hop: str
    url: str
    title: str
    snippet: str
    relevance: float

    @property
    def estimated_tokens(self) -> int:
        return estimate_tokens(self.snippet)


@dataclass
class EvidenceBundle:
    """The enumerated evidence set handed to the prompt (B) and persisted (A)."""

    claim: str
    items: list[PackedEvidence] = field(default_factory=list)
    dropped: int = 0

    @property
    def token_estimate(self) -> int:
        return sum(item.estimated_tokens for item in self.items)

    def labels(self) -> list[str]:
        return [item.label for item in self.items]

    def as_prompt_block(self) -> str:
        """Render the bundle as labelled blocks; ids and URLs come only from us."""
        return "\n\n".join(
            f"[{item.label}] {item.title} — {item.url}\n{item.snippet}" for item in self.items
        )


def pack_evidence(
    claim: str,
    wiki_evidence: list[WikiEvidence] | None = None,
    source_evidence: list[SourceEvidence] | None = None,
    *,
    token_budget: int = DEFAULT_TOKEN_BUDGET,
) -> EvidenceBundle:
    """Rank and pack hop-1 + hop-2 snippets into a labelled, budgeted bundle.

    Empty snippets (e.g. a cited source that failed to fetch) are skipped, so
    unretrievable sources never masquerade as evidence.
    """
    candidates: list[dict] = []
    for item in wiki_evidence or []:
        if item.snippet.strip():
            candidates.append(
                {"hop": "wiki", "url": item.url, "title": item.title, "snippet": item.snippet}
            )
    for item in source_evidence or []:
        if item.snippet.strip():
            candidates.append(
                {
                    "hop": "cited_source",
                    "url": item.url,
                    "title": item.title,
                    "snippet": item.snippet,
                }
            )

    if not candidates:
        return EvidenceBundle(claim=claim)

    scores = _bm25_scores(claim, [candidate["snippet"] for candidate in candidates])
    ranked = sorted(range(len(candidates)), key=lambda index: (-scores[index], index))

    selected: list[tuple[int, float]] = []
    used_tokens = 0
    dropped = 0
    for index in ranked:
        snippet = candidates[index]["snippet"]
        tokens = estimate_tokens(snippet)
        if used_tokens + tokens <= token_budget:
            pass
        elif not selected:
            # Always keep at least one snippet; truncate it to fit the budget.
            snippet = _truncate_to_tokens(snippet, token_budget)
            candidates[index]["snippet"] = snippet
            tokens = estimate_tokens(snippet)
        else:
            dropped += 1
            continue
        selected.append((index, scores[index]))
        used_tokens += tokens

    # Stable output order: hop-1 before hop-2, original order within each hop.
    selected.sort(key=lambda pair: (_HOP_ORDER[candidates[pair[0]]["hop"]], pair[0]))

    items: list[PackedEvidence] = []
    counters = {"wiki": 0, "cited_source": 0}
    for index, relevance in selected:
        candidate = candidates[index]
        counters[candidate["hop"]] += 1
        prefix = "W" if candidate["hop"] == "wiki" else "S"
        items.append(
            PackedEvidence(
                label=f"{prefix}{counters[candidate['hop']]}",
                hop=candidate["hop"],
                url=candidate["url"],
                title=candidate["title"],
                snippet=candidate["snippet"],
                relevance=round(relevance, 6),
            )
        )
    return EvidenceBundle(claim=claim, items=items, dropped=dropped)


def store_evidence(check_run, bundle: EvidenceBundle) -> list[object]:
    """Persist a bundle onto the Chunk A ``Evidence`` table (hop + labels per §4).

    Replaces any prior evidence for the run so re-packing is idempotent.
    """
    from apps.checks.models import Evidence

    Evidence.objects.filter(check_run=check_run).delete()
    rows = [
        Evidence(
            check_run=check_run,
            hop=item.hop,
            url=item.url[:2048],
            title=item.title[:512],
            snippet=item.snippet,
            relevance=item.relevance,
        )
        for item in bundle.items
    ]
    Evidence.objects.bulk_create(rows)
    return rows
