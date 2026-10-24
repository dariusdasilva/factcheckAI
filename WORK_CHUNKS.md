# FactCheckAI — Work Chunks

Four parallel work packages. Run order: **A starts immediately**; B, C, D branch off A's interface contracts (contract freeze = end of week 2). Each chunk ends with named, testable deliverables — "done" is the acceptance test passing, not "looks finished".

```
        ┌─────────────────────────┐
        │  CHUNK A — Backend core │  (foundation; starts now)
        └────────┬────────────────┘
        contracts frozen end of week 2
             ├───────────────┬───────────────┐
             ▼               ▼               ▼
      ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
      │ B Inference │ │ C Evidence  │ │ D Clients   │
      └─────────────┘ └─────────────┘ └─────────────┘
```

---

## CHUNK A — Backend core, data model & async plumbing  *(also the integration owner)*

**Owns:** `config/`, `apps/checks/`, `apps/accounts/`, CI, deployment basics.

| # | Deliverable | Acceptance test |
|---|---|---|
| A1 | Django 5 + DRF skeleton, settings split, health endpoint | `GET /api/v1/health/` returns 200 JSON w/ DB ok |
| A2 | Models: `Claim`, `CheckRun`, `Evidence`, `Source`, `ApiKey` (hashed), `ModelSetting`, `AuditLog` + migrations | `pytest` model tests green |
| A3 | `POST/GET /checks/`, `PUT /settings/model/`, `GET /spend/`, `/models/` **stub** | API tests green; 202-then-poll works |
| A4 | Task queue wired (Django-Q2), throttling, token+session auth | slow "fake check" task completes; throttle blocks #101 |
| A5 | CI (lint+test on push), README setup section | green badge |

**Interface A hands to B/C/D (freeze wk2):** REST contract above (skip to §3 ARCHITECTURE.md) and the `InferenceResult` dataclass.

**Wins early because:** everything else hangs off these endpoints; A also babysits merges.

---

## CHUNK B — Inference engine: fallback chain, circuit breaker, models & spend

**Owns:** `apps/inference/` only.

| # | Deliverable | Acceptance test |
|---|---|---|
| B1 | `RemoteLLMProvider` (OpenRouter) + `OllamaProvider` (`gemma4:e4b-it-qat`), behind one interface, `InferenceService.check()` | mocked test calls each provider |
| B2 | **Circuit breaker**: 3 fails → 60 s cooldown → auto-recover | test: kill API → falls to Ollama; kill both → `fail_state`, never fabricates |
| B3 | Model catalog: fetch OpenRouter `/models`, filter Gemma, cache 24 h; `/models/` returns API-tab **+ Ollama `/api/tags` local-tab (installed only)** | catalog test; local tab empty when nothing pulled |
| B4 | Cost estimator + spend ledger (prices snapshotted onto CheckRun) + spend cap ($5 → 100% drops to local tier) | price-snapshot test; cap-overrun drops tier |
| B5 | Latency cut-off (fail → fail_state if > 90 s) | slow-mock test |

**Depends on:** A2 (CheckRun fields), A3 endpoints. **Hands to D:** result JSON shape per §2.2 incl. statuses `ok | fallback | fail_state` and "local mode" indicator.

---

## CHUNK C — Wikipedia evidence pipeline

**Owns:** `apps/sources/`.

| # | Deliverable | Acceptance test |
|---|---|---|
| C1 | Discovery: claim keywords → MediaWiki `list=search` → ≤3 articles | canned-Wiki-API test |
| C2 | Article read (`page/summary` + extracts) → hop-1 evidence `W*` | two-article fixture returns texts |
| C3 | Citation extraction (`prop=extlinks` + reference parse) → dedupe/archive-strip | fixture w/ known refs |
| C4 | Source fetch (top 3–5, text extraction, 1 MB cap) → hop-2 `S*` + `Source` cache | cache hit = no refetch (double-call test) |
| C5 | Politeness layer: UA + `maxlag=5`, 1 req/s/host, 10 s timeout, type allowlist | rate-limiter unit test |
| C6 | Evidence packer → labelled bundle in token budget; VCR-style recorded fixtures for the whole pipeline | packer test; fixtures committed |

**Depends on:** A2 (`Source`/`Evidence`). **Hands to B:** `evidence[]` into the prompt; **to D:** "crawling Wikipedia…" stage labels (for future SSE polish); **to M7:** the eval set runs through this.

---

## CHUNK D — Clients: web app + Firefox extension

**Owns:** `frontend/web/`, `extension/`.

| # | Deliverable | Acceptance test |
|---|---|---|
| D1 | Web: auth + submit form + result render + history | manual script + Playwright smoke |
| D2 | Web: polling progress + "local mode" / "degraded" banners (fail state is a *banner*, never a fabricated verdict) | wire mock API states |
| D3 | Extension MV3: manifest, popup, selection capture, API-key options | `web-ext lint` clean; manual FF test |
| D4 | Extension: same polling + status badge overlay incl. neutral fail-state badge | manual fail-state test vs local down-API |
| D5 | Settings pages in both: model pickers (API tab w/ costs, local tab installed-only) + spend readout | served from `/models/`, `/spend/` |

**Depends on:** A3 contract frozen. **Mock the API first** (static JSON per §2.2) so D can start before A3 real — this is the chunk most exposed to integration slip.

---

## Suggested cadence (8 weeks → M1–M7 of ARCHITECTURE.md §8)

| Wk | Chunks |
|---|---|
| 1 | A1 + D mock-API contract review together (contract freeze is joint sign-off) |
| 2 | A2–A3 (contract freeze at end); B1, C1–C2 start on mocks; D1 |
| 3–4 | A4–A5; B1–B2 real; C2–C4; D2, D3 |
| 5–6 | B3–B5; C5–C6; D4–D5 — **first end-to-end check lands here** |
| 7 | integration bugs; eval set (§9 Q3) runs through pipeline |
| 8 | hardening + demo (M7) |

**Cross-chunk rules:**
- One PR rule: nobody merges without a green CI (A owns) — keeps parallel work from merging blind.
- Fixture-first for anything networked (C records real responses; B uses recorded OpenRouter bodies) so tests never hit live APIs.
- The fail-state contract (never invent a verdict, status strings exact) is shared law across B and D — changes need all-hands call.
