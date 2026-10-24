# FactCheckAI

![CI](https://github.com/dariusdasilva/factcheckAI/actions/workflows/ci.yml/badge.svg)

A fact-checking assistant: submit a claim, the system gathers Wikipedia evidence
(and the sources those articles cite), runs it past a Gemma model, and returns a
verdict with evidence and a confidence rating — served by one Django REST API to
both a web app and a Firefox extension.

**The core reliability law (AGENTS.md §2):** the system *never fabricates a verdict*.
If inference is unavailable, responses carry `"status": "fail_state"` and the UIs
show a degradation banner — never a plausible-looking made-up answer.

## Status (WORK_CHUNKS.md)

| Chunk | Scope | Status |
|---|---|---|
| **A** | Backend core: skeleton, models, REST contract, queue/throttle/auth, CI | ✅ done |
| **B** | Inference engine: fallback chain, circuit breaker, catalog, spend | pending (A's contract frozen) |
| **C** | Wikipedia evidence pipeline (two-hop crawl) | pending |
| **D** | Web app + Firefox MV3 extension | pending |

## Stack

Python 3.12 · Django 5 + DRF · django-q2 (ORM broker — no Redis for dev) ·
SQLite (dev) / PostgreSQL (prod) · Gemma via OpenRouter (remote) and Ollama
`gemma4:e4b-it-qat` (local tier) · JavaScript web app + MV3 extension.

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

cp env.example .env          # defaults are fine for local dev
python manage.py migrate
```

Run the API and the task worker in two terminals:

```bash
python manage.py runserver    # terminal 1: http://127.0.0.1:8000
python manage.py qcluster     # terminal 2: picks up queued checks
```

Sanity-check the public health endpoint:

```bash
curl -s http://127.0.0.1:8000/api/v1/health/
# {"status":"ok","service":"factcheckai-api","components":{"database":"ok","queue":"ok"}}
```

### Trying the checks API

Auth is session (web app) or token (extension). To mint a token for manual testing:

```bash
python manage.py createsuperuser
python manage.py shell
```

```python
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token

u = User.objects.get(username="your-admin")
print(Token.objects.get_or_create(user=u)[0].key)   # copy this
```

Then submit a claim and poll it (202-then-poll contract):

```bash
TOKEN=...
curl -s -X POST http://127.0.0.1:8000/api/v1/checks/ \
  -H "Authorization: Token $TOKEN" -H "Content-Type: application/json" \
  -d '{"claim": "Drinking coffee cures the common cold."}'
# 202 {"check_id": 1, "status": "queued"}

curl -s http://127.0.0.1:8000/api/v1/checks/1/ -H "Authorization: Token $TOKEN"
```

> Until Chunk B lands, the worker is a placeholder that completes runs as
> `ok` / `unverified` after a short delay (`FAKE_CHECK_LATENCY_S`, default 2 s).
> `unverified` is the honest "no model judged this" mark — never a fabricated verdict.

## API surface (v1)

Base: `/api/v1/` · JSON only · session or token auth · 100 req/day/user throttle
(health is exempt — clients use it as a pre-flight degradation probe).

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v1/checks/` | Submit a claim → `202` + `check_id` |
| `GET` | `/api/v1/checks/{id}/` | Poll result — terminal statuses `ok` \| `fallback` \| `fail_state` |
| `GET` | `/api/v1/checks/` | List your past checks (paginated) |
| `GET` | `/api/v1/health/` | Public liveness: DB + queue components |
| `GET` | `/api/v1/models/` | Model picker data — **stub** until Chunk B3 (live OpenRouter/Ollama catalogs) |
| `PUT` | `/api/v1/settings/model/` | Set your default model per tier (`api` / `local`) |
| `GET` | `/api/v1/spend/` | Estimated spend — **stub** until Chunk B4's ledger |
| `POST` | `/api/v1/sources/` | Extension pushes scraped page text into the crawl cache |
| `POST` | `/api/v1/auth/keys/` | Create an extension bearer key (shown once, stored hashed) |

Frozen contracts (names, status strings, `InferenceResult`) live in
`apps/checks/contracts.py` — changes there are cross-chunk changes and need an
all-hands call.

## Quality checks

```bash
ruff check .
pytest
```

CI runs both on every push (`.github/workflows/ci.yml`). Tests are **hermetic** —
no live API calls anywhere; networked chunks use recorded fixtures (see
CI_CD.md). Nobody merges with a red `main`.

Extension checks (Chunk D, once `extension/` exists):

```bash
npx web-ext lint --source-dir=extension
```

## Configuration

Secrets and deployment-specific values come from env vars or the gitignored
`.env` (django-environ). See `env.example` for every variable and its default.
Never commit secrets; `.env` is gitignored.

## Repo layout

```
config/            Django settings (base/dev/prod), urls, wsgi/asgi
apps/checks/       claims, check runs, evidence, crawl cache, contracts, worker task
apps/accounts/     hashed API keys, per-tier model settings
apps/inference/    Chunk B (fallback chain, circuit breaker)
apps/sources/      Chunk C (Wikipedia pipeline)
frontend/web/      Chunk D web app
extension/         Chunk D Firefox MV3 extension
tests/             pytest suite (hermetic)
```

**Further reading:** `ARCHITECTURE.md` (system design, §2.2 fallback chain, §3
REST contract) · `WORK_CHUNKS.md` (the four work packages + acceptance tests) ·
`CI_CD.md` (pipelines, Render deploy, tag-based extension releases) · `AGENTS.md`
(rules for AI agents and humans working side by side).

## Deploying

Backend deploys on Render per CI_CD.md: `pip install -r requirements.txt`, then
`python manage.py migrate && gunicorn config.wsgi` with
`DJANGO_SECRET_KEY` / `DJANGO_DEBUG=0` / `OPENROUTER_API_KEY` set. Postgres via
`DATABASE_URL`. Ollama stays on the demo laptop (the fallback chain demo is
API-down → local Ollama by design). Tag `v*` to auto-build the extension zip
into a GitHub Release.
