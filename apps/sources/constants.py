"""Tunables and endpoint constants for the Wikipedia evidence pipeline.

Everything politeness-related is defined here so the limits live in one place
(ARCHITECTURE.md §3.2 "Politeness & caching rules", §6 Security notes).
"""

from __future__ import annotations

# --- MediaWiki / Wikimedia endpoints (English Wikipedia for the demo) -----------------
WIKI_API_ENDPOINT = "https://en.wikipedia.org/w/api.php"
WIKI_REST_SUMMARY_ENDPOINT = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"

# Wikimedia's User-Agent policy requires an identifiable agent with a contact URL.
USER_AGENT = (
    "FactCheckAI/0.1 "
    "(https://github.com/factcheckai/factcheckai; factcheckai-hackathon@example.com) "
    "python-requests"
)

# --- Politeness limits (non-negotiable: a condition of talking to Wikimedia) ----------
MAXLAG_SECONDS = 5
PER_HOST_MIN_INTERVAL_SECONDS = 1.0  # 1 request at a time, >= 1 s spacing per host
DEFAULT_TIMEOUT_SECONDS = 10.0
MAX_PAGE_BYTES = 1_000_000  # ~1 MB raw cap per fetched source

# Content-type allowlist. API endpoints answer with JSON; article/source fetches with
# HTML/XHTML/plain text; cited primary sources are sometimes PDFs (§3.2 stage 4).
ALLOWED_CONTENT_TYPES = frozenset(
    {
        "application/json",
        "text/html",
        "application/xhtml+xml",
        "text/plain",
    }
)
PDF_CONTENT_TYPE = "application/pdf"

# --- Discovery -------------------------------------------------------------------------
DISCOVERY_ARTICLE_LIMIT = 3  # §3.2 stage 1: cap at 2–3 articles

# --- Citation extraction (§3.2 stage 3) -----------------------------------------------
# Archive/redirect services are stripped: checking a web-archive copy tells us nothing
# the live source wouldn't, and it bloats the bundle.
ARCHIVE_HOSTS = frozenset(
    {
        "archive.org",
        "web.archive.org",
        "archive.ph",
        "archive.is",
        "archive.today",
        "webcache.googleusercontent.com",
    }
)
# Social media and wiki mirrors are dropped: low-quality or circular evidence.
SOCIAL_HOSTS = frozenset(
    {
        "twitter.com",
        "x.com",
        "facebook.com",
        "instagram.com",
        "youtube.com",
        "tiktok.com",
        "reddit.com",
        "pinterest.com",
        "linkedin.com",
    }
)
WIKI_MIRROR_HOSTS = frozenset(
    {
        "wikipedia.org",
        "en.wikipedia.org",
        "en.m.wikipedia.org",
        "simple.wikipedia.org",
        "wikimedia.org",
        "commons.wikimedia.org",
        "wikidata.org",
        "wikisource.org",
        "wiktionary.org",
    }
)
EXTLINKS_MAX_PAGES = 5  # safety cap on continuation loops

# --- Caching (§3.2 "everything cached": articles 7 d, sources 7 d, search 24 h) -------
SEARCH_CACHE_TTL_SECONDS = 24 * 60 * 60
ARTICLE_CACHE_TTL_SECONDS = 7 * 24 * 60 * 60

# --- robots.txt compliance (§6: robots respected for all non-Wikipedia sources) -------
ROBOTS_CACHE_TTL_SECONDS = 24 * 60 * 60
ROBOTS_ERROR_BACKOFF_SECONDS = 300  # don't hammer hosts whose robots.txt 5xx-es

# --- Source fetch / cache (§3.2 stage 4, §5) ------------------------------------------
# Hop-2 fan-out is a single user-facing knob: fast=0, balanced=3, deep=5.
EVIDENCE_DEPTH_OPTIONS = {"fast": 0, "balanced": 3, "deep": 5}
DEFAULT_EVIDENCE_DEPTH = "balanced"
# Articles and cited sources are cached for 7 days; repeated checks cost no network.
SOURCE_CACHE_TTL_SECONDS = 7 * 24 * 60 * 60
# Cited-source text is capped before packing (same ~1 MB raw cap as the fetch guard).
MAX_SOURCE_TEXT_CHARS = 1_000_000
# §3.2 stage 4: ~2,000 tokens packed *per source* (chars/4 estimator), so one long
# page can never crowd out all other hop-1/hop-2 evidence in the token budget.
SOURCE_SNIPPET_MAX_TOKENS = 2_000
SOURCE_SNIPPET_MAX_CHARS = SOURCE_SNIPPET_MAX_TOKENS * 4

# Primary sources get a ranking boost (§3.2 stage 4): checking the original claim
# beats re-reading another secondary summary.
PRIMARY_SOURCE_SUFFIXES = (
    ".gov",
    ".gov.uk",
    ".ac.uk",
    ".edu",
    ".mil",
    ".int",
)
PRIMARY_SOURCE_HOSTS = frozenset(
    {
        "doi.org",
        "dx.doi.org",
        "ncbi.nlm.nih.gov",
        "pubmed.ncbi.nlm.nih.gov",
        "who.int",
        "un.org",
    }
)

# --- Evidence packer (§3.2 stage 5) ---------------------------------------------------
DEFAULT_TOKEN_BUDGET = 6000

