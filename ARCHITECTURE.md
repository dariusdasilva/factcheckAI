# Fact-Checker AI — Architecture Design Document

**Version:** 0.1 (draft for team review)
**Date:** 2026-10-24
**Stack:** Python 3.11+ · Django 5 + Django REST Framework · JavaScript (browser) · Gemma (any variant, e.g. Gemma 4) via API + local Ollama
**Platforms:** Web application + Firefox WebExtension

---

## 1. Overview

A fact-checking AI system that takes a claim (typed text, selected text on a web page, or pasted article text) and returns a verdict with evidence and a confidence rating.

The core reliability requirement is the **inference fallback chain**:

1. **Primary** — remote Gemma API (e.g. Google Gemini API serving Gemma, or an OpenRouter-compatible endpoint). Fast, no local hardware needed.
2. **Secondary** — local Gemma via **Ollama** on the host machine. Used automatically when the API is unreachable, rate-limited, or returns errors.
3. **Fail state** — if both fail, the system enters a defined "fail state": it never invents a result, it tells the user the service is degraded and optionally queues the request for retry.

A single Django REST API serves **both** clients: the web app and the Firefox extension. The extension is a thin client — it talks to the same REST endpoints and adds only selection/scrape capture UI.

```
                        ┌──────────────────────┐
                        │   Django (DRF)       │
  ┌──────────────┐      │  ┌────────────────┐  │
  │  Web App     ├─────▶│  │  REST API      │  │
  │  (JS)        │      │  │  /api/v1/...   │  │
  └──────────────┘      │  └───────┬────────┘  │
                        │          │           │
  ┌──────────────┐      │  ┌───────▼────────┐  │
  │  Firefox     ├─────▶│  │ Inference      │  │
  │  Extension   │      │  │ Service        │  │
  │  (JS)        │      │  │ (fallback      │  │
  └──────────────┘      │  │  chain)        │──┼──▶ Remote Gemma API
                        │  └───────┬────────┘  │──▶ Ollama (localhost:11434)
                        │          │           │
                        │  ┌───────▼────────┐  │
                        │  │  PostgreSQL/   │  │
                        │  │  SQLite        │  │
                        │  └────────────────┘  │
                        └──────────────────────┘
```

---

## 2. Components

### 2.1 Django backend (Python)

| Piece | Choice | Why |
|---|---|---|
| Web framework | Django 5.x | Batteries-included: ORM, admin, auth, migrations |
| API layer | Django REST Framework (DRF) | Serializers, viewsets, throttling, browsable API |
| Auth | DRF Token auth + session auth for the web app | Extension needs a key; web app can use sessions |
| Task queue | Django-Q2 (or Celery + Redis if we outgrow it) | Fact-checks can take 10–60 s; must not block HTTP workers |
| Database | SQLite for dev / PostgreSQL for deployment | Django ORM makes this a settings switch |
| Cache | Redis (or LocMem in dev) | Rate limiting, response caching, circuit-breaker state |

**Django apps:**

- `checks/` — claims, check runs, verdicts, evidence (core domain)
- `inference/` — LLM clients, fallback chain, prompt templates
- `sources/` — **Wikipedia evidence pipeline**: article discovery, citation extraction, cited-source fetching, text extraction, caching (§3.2)
- `accounts/` — API keys, user management (thin; mostly use stock Django auth)

### 2.2 Inference service (the fallback chain) — Python, inside `inference/` app

A single `InferenceService.check(prompt: str) -> InferenceResult` entry point. Internally it walks a list of **providers in priority order** and tracks per-provider health with a **circuit breaker**.

```
request ──▶ provider[0] = RemoteAPI
              │ on timeout / 5xx / 429 / network error
              ▼
           provider[1] = Ollama (http://localhost:11434)
              │ on startup failure / connection refused / timeout
              ▼
           FAIL STATE ──▶ return IsFallback graceful error
                          + retry policy
```

#### API provider of record: **OpenRouter** (decided 2026-10-24)

- OpenRouter gives us one OpenAI-compatible endpoint and a **public catalog API** listing every model with per-1M-token input/output prices. We need that catalog anyway for the user-facing model picker, so the choice costs us zero extra work.
- It carries all Gemma variants (community- and Google-hosted), so the picker can show every downloadable-API model with real price estimates. Google's Gemini API serves a much shorter Gemma list.
- Google stays a documented alternative: because the remote tier is coded against a `RemoteLLMProvider` interface, a `GoogleGeminiProvider` class can be added later without touching the fallback chain or model-selection design.
- Open question moved out of §9: what remains is picking an owner for the account/key and setting the **monthly spend cap** (see §3.1).

**Circuit breaker rules (implemented in Python, no infra needed):**

- After **N consecutive failures** (default 3) a provider is marked *down* for a **cooldown** (default 60 s). Requests skip it during cooldown, then test it once before restoring.
- The API provider is tried again on cooldown expiry — if it recovers, the chain flips back automatically. Local provider staying down longer sets a "degraded_hardware" warning.
- **Fail state response** (never fabricated):
  ```json
  {
    "status": "fail_state",
    "detail": "Both inference providers are currently unavailable.",
    "retry_after": 60,
    "providers_tried": ["remote_api", "ollama"]
  }
  ```
  The UI surfaces this as an explicit banner (not a fake verdict), and the extension infers a neutral badge.

**InferenceResult fields:** `verdict`, `confidence`, `evidence[]`, `raw_model_output`, `provider_used`, `latency_ms`, `status` (`ok` | `fallback` | `fail_state`).

### 2.3 Web app (JavaScript)

- Static SPA served by Django (templates for first paint, vanilla JS or a small framework — decide with the team; vanilla keeps the toolchain simple).
- Auth flows, claim submission, check progress via **polling `/checks/{id}/` (decided — see §9)**, history of past checks, admin view of sources. SSE progress streaming is an M6 stretch goal behind the same status-subscription interface.

### 2.4 Firefox extension (JavaScript, WebExtensions API)

- **manifest.json** (MV3): `content_scripts` to capture selected text, a popup for submitting a check, `optional_host_permissions` for the API origin.
- Calls the same `/api/v1/checks/` endpoint with an API key the user pastes into extension options.
- Injects a badge/overlay on the page with the verdict, plus a "fail state" neutral state.
- No business logic in the extension — all inference lives in Django. This keeps one brain, two faces.

---

## 3. REST API (v1)

Base: `/api/v1/` · JSON only · token or session auth · 100 req/day/user default throttle (DRF).

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v1/checks/` | Submit a claim for fact-checking. Returns `202` + `check_id`; result fetched or pushed later |
| `GET` | `/api/v1/checks/{id}/` | Poll result (web + extension). Body per §2.2 |
| `GET` | `/api/v1/checks/` | List user's past checks |
| `GET` | `/api/v1/health/` | Providers, DB, queue health. Public. Used by both clients to pre-emptively show "degraded" state |
| `GET` | `/api/v1/models/` | Populates the model pickers — API: **all available Gemma models with cost-per-check estimates**; Local: **only models already pulled in Ollama** |
| `PUT` | `/api/v1/settings/model/` | Set the user's default model (API tier and/or local tier) |
| `GET` | `/api/v1/spend/` | Estimated spend: month-to-date, by provider, and average cost per check |
| `POST` | `/api/v1/sources/` | Store scraped source text (extension can push page text) |
| `POST` | `/api/v1/auth/keys/` | Create API key |

** POST /checks/ request example:**

```json
{
  "claim": "Drinking coffee cures the common cold.",
  "context": {"source_url": "https://example.com/article", "selection": true}
}
```

**Enrichment hook:** before inference, the system retrieves supporting snippets via the **Wikipedia evidence pipeline** (§3.2); pluggable via an `EvidenceProvider` interface so non-Wikipedia sources can be added later.

### 3.1 Model picker & spend estimation (user-facing feature)

Two tabs in settings (same picker in web app and extension options):

**API tab — every model, with spend estimates.**

- Source: OpenRouter's public `/models` catalog, filtered to the Gemma family, cached in Redis for 24 h (manual refresh button for staleness).
- Each row: model id, context window, input/output price per 1M tokens straight from the catalog, plus a **cost-per-check estimate**: `est_tokens ≈ chars/4` for the prompt (claim + scaffold + evidence snippets) × input price, plus a fixed assumed output length (default 512 tokens) × output price.
- Month-to-date **estimated spend** shown at the top of the tab, from our own ledger (see data model). Each CheckRun stores the input/output prices *at call time*, so historical rows stay correct even if OpenRouter prices change.
- **Spend cap:** user-set monthly cap (default $5). At 90% we warn; at 100% new checks are refused on the API tier with a clear message and dropped to the local tier, so a runaway loop burns Ollama time, not credit.

**Full Gemma catalog on OpenRouter (snapshot 2026-10-24, verified live against `/api/v1/models`):**

| Model ID | Context | $ / 1M in | $ / 1M out | ≈ cost per check¹ | Notes |
|---|---|---|---|---|---|
| `google/gemma-4-26b-a4b-it` | 262k | $0.0675 | $0.225 | ≈ $0.00032 | Gemma 4, MoE (A4B = 4B active), multimodal |
| `google/gemma-4-26b-a4b-it:free` | 262k | free | free | $0 | Free tier — rate-limited; ideal default for students |
| `google/gemma-4-31b-it` | 262k | $0.20 | $0.40 | ≈ $0.00081 | Largest Gemma 4 dense model, multimodal |
| `google/gemma-4-31b-it:free` | 262k | free | free | $0 | Free tier |
| `google/gemma-3-4b-it` | 131k | $0.04 | $0.05 | ≈ $0.00015 | Cheapest paid — good bulk-check workload model |
| `google/gemma-3-12b-it` | 131k | $0.05 | $0.15 | ≈ $0.00023 | Balanced cost/quality |
| `google/gemma-3-27b-it` | 131k | $0.08 | $0.35 | ≈ $0.00042 | Strong Gemma 3 flagship |
| `google/gemma-2-27b-it` | 8k | $0.65 | $0.65 | ≈ $0.00230 | Legacy; small context — exclude from picker default? |

¹ Per-check estimate at ~3,000 input tokens (claim + scaffold + evidence snippets) and 512 output tokens (§3.1 formula). This table is **illustrative** — the picker always renders the live catalog, since models and prices change.

**Picker design consequences:**

- Hide `gemma-2-27b-it` behind an "include legacy" toggle — the 8k context is too small for evidence-rich prompts.
- Default API model: `gemma-4-26b-a4b-it:free` (zero spend; the paid 26B A4B is identical weights without rate limits, so a sensible paid fallback choice).
- Because all sizes share the same prompt format, we can keep one prompt template and let users compare verdict quality across model sizes cheaply.

**Local tab — downloaded models only.**

- **Canonical local model tag: `gemma4:e4b-it-qat`** (decided 2026-10-24, §9). All team README/docker instructions use exactly this tag so Ollama pulls match.
- **Why the QAT tag and not the bare `gemma4:e4b`:** the default `gemma4:e4b` weighs 6.6–9.5 GB depending on context resolution — an unpredictable footprint — while `e4b-it-qat` is a fixed, smaller **6.1 GB** trained with **quantization-aware training (QAT)**. QAT teaches the model to expect its own low-precision weights, so quality doesn't crater the way naive post-hoc 4-bit quantization does; Google ships it specifically to deliver ≈ BF16 quality at ~3× less memory. For a fact-checker, **verdict quality is the product** — the fallback tier exists so checks *still work* when the API is down, and a degraded-quality local verdict with too-low confidence would quietly undermine trust in every result. QAT is the cheapest way to protect quality while keeping the tier small enough for the team's mixed laptops.
- Practical notes: 128k context, multimodal, only ~4B active params (MoE) so CPU-only laptops stay fast; GPU not required. Documented hardware floor if a member's machine can't fit it: `gemma4:e2b-it-qat` (4.3 GB, weaker reasoning — use only as last resort). Guard in code: the Ollama provider validates the *exact* installed tag at `/health/` time and logs a warning if someone has pulled a non-QAT or wrong-size variant, since silent tag drift would make "local mode" behave differently between team members' machines. The `/api/tags` picker still shows whatever is actually installed; the canonical tag is the default `ModelSetting` for the local tier.

- Source: Ollama's `GET /api/tags`, which lists **only models already pulled** on the host. We never advertise a model the user doesn't have.
- Empty state: a copyable `ollama pull …` command and a link to the Gemma library; and if the local tier has no installed model, `/health/` reports `local_missing` so both UIs show it before a check is submitted.
- No pricing shown locally — Ollama has no catalog prices, and showing cost estimates we can't compute would be misleading.

**Selection storage:** per-user `ModelSetting` rows (one for the API tier, one for the local tier) with sensible defaults (cheapest-capable API model; first installed local model). The fallback chain reads these at request time, and `/health/` reflects whether the *chosen* models are reachable, not just any model.

### 3.2 Wikipedia evidence pipeline (decided 2026-10-24) — claim → Wikipedia → its cited sources

Evidence gathering is a **two-hop crawl**: (1) find the Wikipedia articles relevant to the claim, (2) check against them, then (3) pull the sources *those articles cite* and check against the primary sources too. Labelled evidence ids flow into the prompt so every verdict line cites a hop.

```
claim ──▶ 1. DISCOVERY      search queries → MediaWiki search API → top N articles
   │     2. ARTICLE READ    extracts + lead/context from each article
   │     3. CITE EXTRACT    prop=extlinks / reference parsing → cited URLs per article
   │     4. SOURCE FETCH    top N cited URLs → text extraction → cached
   ▼     5. PACK & PROMPT   rank snippets → labelled evidence bundle → Gemma
verdict [W1..Wn primary wiki] [S1..Sm source cited by W1/W2..] + confidence
```

**Stage details:**

1. **Discovery** — extract keywords from the claim (or ask Gemma for 2–3 search queries if keywords are poor) → `action=query&list=search` on `en.wikipedia.org`. Cap at 2–3 articles.
2. **Article read** — `REST /page/summary/` + `action=parse` or `prop=extracts` for the relevant sections. The article text is **hop 1 evidence** (`W1`, `W2`, …).
3. **Citation extraction** — `action=query&prop=extlinks` (programmatic list of external URLs per article) plus reference parsing where needed. Filter URLs: strip citation archives (archive.org), dedupe by domain, drop social/wiki mirrors.
4. **Source fetch (hop 2)** — follow up to **5 cited URLs per claim** *(configurable; more = slower + ruder to hosts)*. Extract clean text (trafilatura or Readability-style), cap ~1 MB raw / ~2,000 tokens packed per source. Prefer primary sources (govt/edu/doi/journal domains get ranking boost) — the whole point of hop 2 is checking the *original* claims Wikipedia summarises, not another secondary rehash.
5. **Pack & prompt** — rank all snippets against the claim (keyword-embedding overlap, no extra model call), fill a token budget (default 6k), label each snippet `[W…]`/`[S…]` with its source URL. Prompt requires the verdict to reference evidence ids and to say explicitly when hop-1 (Wikipedia) and hop-2 (cited source) *agree or disagree*.

**Prompting rule of thumb encoded in the template:** when hop-2 sources contradict the Wikipedia article's framing, that contradiction is surfaced in the output as its own line — Wikipedia is treated as a lead generator, never as ground truth.

**Politeness & caching rules (non-negotiable — a Wikipedia-facing app must respect limits):**

- All MediaWiki/API requests set `maxlag=5` and our standard **User-Agent** per Wikimedia's UA policy; HTTP/2 keep-alive to reuse connections.
- **Everything cached** in the `Source` table keyed by URL + content hash: articles 7 days, sources 7 days, search results 24 h — repeated checks on the same topic cost the network nothing after first pass.
- Outbound crawl concurrency to any single host: **1 request at a time**, ≥1 s spacing, 10 s timeout, content-type allowlist (HTML/PDF only).
- Hop limits expose a single `evidence_depth` setting (`fast`=0 sources, `balanced`=3, `deep`=5) so users choose their own latency.



---

## 4. Data model (core tables)

| Table | Key fields |
|---|---|
| `Claim` | `id`, `text`, `source_url`, `created_by FK`, `created_at` |
| `CheckRun` | `id FK claim`, `status` (queued/running/ok/fallback/fail_state), `provider_used`, `model_id`, `tokens_in`, `tokens_out`, `price_in_per_mtok`, `price_out_per_mtok` (prices captured at call time — spend ledger), `confidence`, `verdict_enum` (true/false/unverified), `latency_ms`, started/finished |
| `Evidence` | `FK CheckRun`, `hop` (`wiki`/`cited_source`), `url`, `title`, `snippet`, `relevance` |
| `Source` | `url` (unique + `content_hash`), `domain`, `fetch_status`, `text_extract`, `fetched_at` — the crawl cache; check that a URL needs re-fetching before spending network |
| `ApiKey` | `FK user`, `key_hash`, `created_at`, `revoked_at` |
| `ModelSetting` | `FK user`, `tier` (`api`/`local`), `model_id`, `spend_cap_monthly` (API tier only) |
| `AuditLog` | `FK CheckRun`, `event`, `json_payload` — for the fail state + fallback telemetry |

Admin views of these tables come free with Django admin.

---

## 5. Failure & degradation matrix

| Scenario | Local Ollama | API | Behaviour shown to user |
|---|---|---|---|
| Normal | up | up | API used (fast path) |
| API rate-limited / down | up | down | Auto-fallback to Ollama; UI shows "local mode" indicator |
| Machine busy/model not loaded | down | up | API used; toast "local model unavailable — used API" |
| Both down | down | down | **Fail state**: banner "Service degraded — result unavailable", retry timer, check marked `fail_state` in DB |
| Wikipedia/mediawiki API down or rate-limiting us | — | — | Check proceeds **without hop-1 evidence**; verdict returned at reduced confidence starting "Wikipedia unavailable — unverified". Hop 2 is skipped with it (no articles → no citations) |
| Some cited sources fail to fetch (paywalls, 403, PDF parse failure) | — | — | Not an error: use the ones that succeeded; every skipped source is cached with `fetch_status` and listed as "not retrievable" in the citation list |
| Local latency too high (configurable, e.g. > 90 s) | — | — | Request is failed into fail state, not held forever |

---

## 6. Security notes (must-haves)

- Store API keys **hashed**, never plaintext (extension key is a bearer token).
- CORS: `django-cors-headers` with only the web app origin allow-listed; extension uses `browser.runtime` messaging or explicit origin match.
- Never inject raw UI-claim text into prompts without size limits + prompt-injection scrubbing (strip markdown control, cap at N chars).
- **Wikipedia politeness**: `maxlag=5`, proper User-Agent, caching per §3.2 (a 400-request-a-minute wiki scraper would get the app IP-banned — the throttle below is what prevents it).
- Crawl limits: 1 req/s per host, 10 s timeout, 1 MB max page size, content-type allowlist, per-domain robots respected for all non-Wikipedia sources.
- HTTPS only in deployment; `DEBUG=False`; secret from env.

---

## 7. Repo layout

```
factchecker/
├── ARCHITECTURE.md
├── README.md
├── pyproject.toml
├── manage.py
├── config/            # Django settings (base/dev/prod), urls.py, celery/q config
├── apps/
│   ├── checks/
│   ├── inference/     # providers: remote_api.py, ollama.py, circuit_breaker.py
│   ├── sources/
│   └── accounts/
├── frontend/web/      # web app JS/CSS
├── extension/         # Firefox MV3 extension: manifest.json, popup/, content/
├── tests/             # pytest + DRF APITestCase incl. fallback-chain tests
└── docker-compose.yml # postgres + redis + ollama for local dev
```

---

## 8. Suggested milestones (team break-down)

1. **M1 – Skeleton** (week 1): repo, Django + DRF up, health endpoint, repo CI lint/test. Owner: infra pair.
2. **M2 – Inference core** (weeks 2–3): Ollama client + circuit breaker + fail-state tests. Testable via `manage.py shell`.
3. **M3 – REST + data model** (weeks 3–4): `/checks/`, `/health/`, DB models, throttle, auth keys.
4. **M4 – Web app** (weeks 4–5): submit form, poll result, fallback indicator.
5. **M5 – Extension** (weeks 5–6): MV3 popup + selection capture + status badge.
6. **M6 – Evidence enrichment + admin dashboards** (weeks 6–7).
7. **M7 – Hardening & demo** (week 8): load test of fallback path under API outage, security review, report/demo.

---

## 9. Open questions for the team

1. ~~**Gemma API endpoint of record**~~ — **Decided: OpenRouter** (see §2.2). Remaining sub-tasks: create the account/key, pick the default Gemma model, and assign an owner for the monthly spend cap (§3.1).
2. ~~**Quantization/model size** for local runs~~ — **Decided: `gemma4:e4b-it-qat`** (6.1 GB, 128k ctx, ~4B active params, QAT near-full-precision quality; see §3.1). Fits the team's mixed laptops without needing a GPU. Hardware floor `gemma4:e2b-it-qat` (4.3 GB) documented for machines that can't fit it. One sub-task remains: verify each member's machine can hold 6.1 GB + KV cache at rest before M2.
3. **Which claims to check in the demo?** Defines our evaluation set + how we measure accuracy.
4. ~~**Evidence sources**~~ — **Decided: Wikipedia-first two-hop crawl (§3.2)** — check against Wikipedia, then against the sources it cites. Remaining sub-task: `evidence_depth` default for the demo (`balanced`=3 sources recommended).
5. ~~**Async transport for progress**~~ — **Decided: polling for M3–M5, SSE as a stretch goal in M6.** Same server-side substrate either way (a "status changed" channel per check), so retrofitting SSE later is a rendering change, not a redesign. Polling first avoids adding Channels/ASGI runtime complexity during the busiest build weeks; popup-lifecycle reconnection edge cases in the extension also favour a dumb timer. Revisit only if stage-wise progress ("crawling Wikipedia…") is deemed a demo-day must-have.
