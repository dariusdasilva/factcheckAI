"""C6 acceptance — Evidence packer: labelled bundle inside a token budget.

"Packer test" (WORK_CHUNKS.md, Chunk C). Verifies labelling (``W*`` then ``S*``),
budget enforcement, ranking, empty-snippet skipping, and persistence onto the
Chunk A ``Evidence`` table.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model

from apps.checks.models import CheckRun, Claim, Evidence, EvidenceHop
from apps.sources.article_read import WikiEvidence
from apps.sources.packer import (
    estimate_tokens,
    pack_evidence,
    store_evidence,
)
from apps.sources.source_fetch import SourceEvidence


def _wiki(label: str, snippet: str, title: str = "Coffee") -> WikiEvidence:
    return WikiEvidence(
        label=label,
        pageid=1,
        title=title,
        url=f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}",
        snippet=snippet,
        description="",
    )


def _source(label: str, snippet: str, url: str = "https://www.cdc.gov/x") -> SourceEvidence:
    return SourceEvidence(
        label=label,
        url=url,
        title="cdc.gov",
        snippet=snippet,
        domain="cdc.gov",
        fetch_status="fetched",
    )


CLAIM = "Drinking coffee cures the common cold."


def test_pack_labels_wiki_then_sources():
    bundle = pack_evidence(
        CLAIM,
        [_wiki("W1", "Coffee is a brewed drink."), _wiki("W2", "The common cold is viral.")],
        [_source("S1", "There is no cure for the common cold.")],
    )

    assert bundle.labels() == ["W1", "W2", "S1"]
    assert [item.hop for item in bundle.items] == ["wiki", "wiki", "cited_source"]


def test_pack_skips_empty_snippets():
    bundle = pack_evidence(
        CLAIM,
        [_wiki("W1", "Coffee is a brewed drink.")],
        [_source("S1", ""), _source("S2", "   ")],
    )

    assert bundle.labels() == ["W1"]


def test_pack_respects_token_budget_and_reports_dropped():
    big = "coffee " * 5000  # far larger than the budget
    bundle = pack_evidence(
        CLAIM,
        [_wiki("W1", big), _wiki("W2", big)],
        [_source("S1", big)],
        token_budget=200,
    )

    assert bundle.token_estimate <= 200
    assert bundle.dropped == 2
    assert len(bundle.items) == 1  # at least one snippet survives, truncated


def test_pack_ranks_relevant_snippets_higher():
    relevant = _wiki("W1", "Coffee is a brewed drink prepared from roasted beans.", "Coffee")
    irrelevant = _wiki("W2", "Association football is a team sport.", "Football")

    bundle = pack_evidence(CLAIM, [irrelevant, relevant])
    by_title = {item.title: item for item in bundle.items}

    assert by_title["Coffee"].relevance > by_title["Football"].relevance


def test_pack_empty_corpus():
    bundle = pack_evidence(CLAIM)

    assert bundle.items == []
    assert bundle.labels() == []
    assert bundle.token_estimate == 0


def test_as_prompt_block_carries_labels_and_urls():
    bundle = pack_evidence(CLAIM, [_wiki("W1", "Coffee text.", "Coffee")])

    block = bundle.as_prompt_block()
    assert "[W1]" in block
    assert "https://en.wikipedia.org/wiki/Coffee" in block
    assert "Coffee text." in block


def test_estimate_tokens_is_chars_over_four():
    assert estimate_tokens("") == 1
    assert estimate_tokens("a" * 400) == 100


@pytest.mark.django_db
def test_store_evidence_persists_bundle():
    user = get_user_model().objects.create_user(username="c-packer")
    claim = Claim.objects.create(text=CLAIM, created_by=user)
    check_run = CheckRun.objects.create(claim=claim)
    bundle = pack_evidence(
        CLAIM,
        [_wiki("W1", "Coffee is a brewed drink.")],
        [_source("S1", "There is no cure for the common cold.")],
    )

    rows = store_evidence(check_run, bundle)

    assert len(rows) == 2
    stored = Evidence.objects.filter(check_run=check_run)
    assert stored.count() == 2
    assert {row.hop for row in stored} == {EvidenceHop.WIKI, EvidenceHop.CITED_SOURCE}
    # Snippets are stored with their label preserved as a prefix (model help_text
    # "Labelled snippet"); the DB has no label column (AGENTS.md §4.5: the packer
    # mints ids in memory for the same run).
    assert sorted(row.snippet for row in stored) == [
        "[S1] There is no cure for the common cold.",
        "[W1] Coffee is a brewed drink.",
    ]


@pytest.mark.django_db
def test_store_evidence_is_idempotent():
    user = get_user_model().objects.create_user(username="c-packer-2")
    claim = Claim.objects.create(text=CLAIM, created_by=user)
    check_run = CheckRun.objects.create(claim=claim)
    bundle = pack_evidence(CLAIM, [_wiki("W1", "Coffee is a brewed drink.")])

    store_evidence(check_run, bundle)
    store_evidence(check_run, bundle)

    assert Evidence.objects.filter(check_run=check_run).count() == 1
