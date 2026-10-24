"""Whole-pipeline integration test, replaying recorded Wikipedia responses.

This is the VCR-style end-to-end fixture test required by C6: one claim goes
through discovery → article read → citation extract → source fetch → pack with no
live network, and we assert the labelled bundle and the §5 degradation path.
"""

from __future__ import annotations

import pytest
from conftest import WIKI_API

from apps.checks.models import Source
from apps.sources.pipeline import run_evidence_pipeline

CLAIM = "Drinking coffee cures the common cold."


@pytest.mark.django_db
def test_full_pipeline_from_recorded_fixtures(wiki_api, source_pages, wiki_client, fast_session):
    result = run_evidence_pipeline(CLAIM, client=wiki_client, session=fast_session)

    assert result.degraded is False
    assert [article.title for article in result.articles] == ["Coffee", "Common cold", "Caffeine"]
    assert [item.label for item in result.wiki_evidence] == ["W1", "W2", "W3"]
    assert [item.label for item in result.source_evidence] == ["S1", "S2", "S3"]
    assert result.citations

    labels = result.bundle.labels()
    assert "W1" in labels and "S1" in labels
    assert result.bundle.token_estimate <= 6000
    # Hop-2 fetched three cited sources, cached in the Source table (§3.2).
    assert Source.objects.count() == 3


@pytest.mark.django_db
def test_depth_fast_skips_hop2(wiki_api, wiki_client, fast_session):
    result = run_evidence_pipeline(
        CLAIM, client=wiki_client, session=fast_session, depth="fast"
    )

    assert result.source_evidence == []
    assert result.bundle.labels() == ["W1", "W2", "W3"]
    assert Source.objects.count() == 0


@pytest.mark.django_db
def test_pipeline_degrades_without_hop1_when_wikipedia_down(requests_mock, wiki_client, fast_session):
    requests_mock.get(WIKI_API, status_code=503)

    result = run_evidence_pipeline(CLAIM, client=wiki_client, session=fast_session)

    assert result.degraded is True
    assert result.degrade_reason
    assert result.articles == []
    assert result.bundle.labels() == []
