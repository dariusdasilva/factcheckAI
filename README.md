# FactCheckAI

[![CI](https://github.com/dariusdasilva/factcheckAI_AI-SLOP_HACKATHON_PROJECT/actions/workflows/ci.yml/badge.svg)](https://github.com/dariusdasilva/factcheckAI_AI-SLOP_HACKATHON_PROJECT/actions/workflows/ci.yml)

FactCheckAI checks claims using Wikipedia articles and their cited sources, then
asks a Gemma model for a structured verdict. One Django REST API supports a web
app and a Firefox extension. Remote inference uses OpenRouter, with local Ollama
as the fallback tier.

**Development status:** this is a student project under active development, with
known security, reliability and client-integration gaps. It is not production
ready. The [delivery plan](DELIVERY_PLAN.md) describes the remaining work,
acceptance criteria, ownership and release gates. Track implementation in the
[FAI-01–FAI-48 GitHub backlog](https://github.com/dariusdasilva/factcheckAI_AI-SLOP_HACKATHON_PROJECT/issues?q=is%3Aissue%20FAI-).

## Portfolio goal and hosting budget

The initial release is an employer-facing portfolio demo, targeting **zero recurring hosting cost** with optional, explicitly capped inference spending. Occasional backend downtime and cold starts are acceptable. A paid domain and always-on model hosting are optional future work.

Planned entry points are **Try the demo**, **Watch the walkthrough** and **View the code**. The public showcase will provide screenshots, architecture, a walkthrough and clearly labelled recorded examples without requiring an account. These assets and the hosted showcase are planned, not yet delivered. Sample results must never appear to be newly computed checks.

The full application remains runnable locally. A live hosted backend is optional and will only expose features that pass the applicable security, correctness and spending checks. If it is unavailable, visitors should still be able to explore the showcase and see an honest service status.

See the [portfolio delivery plan](PORTFOLIO_PLAN.md) for initial acceptance and the [full delivery roadmap](DELIVERY_PLAN.md) for the retained 48-task backlog. Production-scale hosting and operational requirements do not block publishing a static showcase; unfinished application tasks remain open.

## Reliability contract

The system must never fabricate a verdict. Preserve the public lifecycle
`queued | running | ok | fallback | fail_state`:

- `ok`: validated remote inference result.
- `fallback`: validated result from the fallback tier.
- `fail_state`: inference unavailable or invalid; no verdict or confidence.

Insufficient evidence is an honest `unverified` verdict from available inference.
It is different from inference being unavailable. Clients must show unavailable
results neutrally. The extension still contains mock verdict generation at the
audit baseline; replacing it is a mandatory release blocker, not an accepted
exception to this contract.

## What exists and what remains

| Area | Current implementation | Remaining work |
|---|---|---|
| Backend | Authenticated submit/poll/history API, models, migrations and Django-Q2 worker | Atomic execution, restart recovery, durable spending and production serving |
| Inference | Remote/local providers, structured parsing, fallback service and internal catalog/spend code | Authoritative citation validation, shared breaker state, complete deadlines and live catalog/spend API integration |
| Evidence | Wikipedia discovery, two-hop retrieval, extraction, packing and caching | Capture provenance, SSRF protection, cross-worker crawl coordination and retrieval quality |
| Web app | Backend-connected submission, polling and history | Safe rendering, recoverable workflows, settings, accessibility and browser acceptance |
| Firefox extension | MV3 popup, options and capture scaffold | Real API submission, configuration, lifecycle/status handling and runtime verification |
| Delivery | CI configuration and documented architecture | Meaningful browser tests, release packaging, deployment, evaluation and operational evidence |

This table describes code and known gaps; it does not certify runtime readiness.
The detailed plan groups all 48 backlog tasks into 19 work packages and seven
acceptance milestones for the full application. The seven P0 tasks block that
application release; a static portfolio showcase has its own narrower acceptance
checklist and must not expose unsafe live features.

## Stack

Python 3.12 · Django 5 + Django REST Framework · Django-Q2 with an ORM broker ·
SQLite for local development / PostgreSQL for deployment · OpenRouter + Ollama ·
vanilla JavaScript web app + Firefox MV3 extension.

The canonical local model is `gemma4:e4b-it-qat`. Model availability and provider
capabilities must be verified against the configured endpoints; documentation is
not a live model catalog.

## Local setup

Clone the repository and enter its directory:

```bash
git clone https://github.com/dariusdasilva/factcheckAI_AI-SLOP_HACKATHON_PROJECT.git
cd factcheckAI_AI-SLOP_HACKATHON_PROJECT
```

Create and activate a Python 3.12 virtual environment.

**Windows PowerShell:**

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
Copy-Item env.example .env
```

**macOS / Linux:**

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
cp env.example .env
```

Edit `.env` for your environment. Keep it private and never commit credentials.
For remote inference, configure `OPENROUTER_API_KEY`. The worker also includes an
alternative Gemini provider selected when only `GEMINI_API_KEY` is configured;
OpenRouter takes precedence when both keys are present. Compatibility and release
scope for the alternative provider still require explicit acceptance.

For local inference, install Ollama separately and pull the configured model:

```bash
ollama pull gemma4:e4b-it-qat
```

Ensure the Ollama service is running and reachable from the worker. By default,
`OLLAMA_BASE_URL` is `http://localhost:11434`. With no remote key configured, the
worker attempts the local tier. If no usable provider is available, the intended
result is `fail_state`.

Initialize the database and create an account:

```bash
python manage.py migrate
python manage.py createsuperuser
```

Run these commands in two terminals, activating the same virtual environment in
each:

```bash
python manage.py runserver    # terminal 1
python manage.py qcluster     # terminal 2
```

Open the development web app at <http://127.0.0.1:8000/> and the admin at
<http://127.0.0.1:8000/admin/>. The worker is required to process queued checks.
The current development SPA routes are enabled by development settings;
production web/static serving is tracked separately.

The public `/api/v1/health/` endpoint checks database connectivity and queue
configuration. Its current response does **not** prove that a worker is consuming
jobs or that the selected inference models are available.

## Trying the API

Create a DRF token for your local test account:

```bash
python manage.py shell
```

```python
from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token

user = get_user_model().objects.get(username="your-admin")
print(Token.objects.get_or_create(user=user)[0].key)
```

Treat the printed token as a secret. The following example uses Bash; substitute
your token locally and poll the returned `check_id` rather than assuming an ID.

```bash
TOKEN=your-local-token
curl -s -X POST http://127.0.0.1:8000/api/v1/checks/ \
  -H "Authorization: Token $TOKEN" -H "Content-Type: application/json" \
  -d '{"claim":"Drinking coffee cures the common cold."}'
# Submission returns HTTP 202 with check_id and status: queued.

curl -s http://127.0.0.1:8000/api/v1/checks/RETURNED_CHECK_ID/ \
  -H "Authorization: Token $TOKEN"
```

Issue an extension key through an authenticated request:

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/auth/keys/ \
  -H "Authorization: Token $TOKEN"
```

The `fcai_…` key is shown once and stored hashed by the backend. Send it as
`Authorization: Token fcai_…` or `Authorization: Bearer fcai_…`. The extension's
end-to-end configuration and API integration remain backlog work.

## API surface

Base path: `/api/v1/`. Checks and account endpoints require authentication.
The default authenticated-user throttle is 100 requests/day; polling quota
semantics remain a delivery-plan decision. Health is public and exempt.

| Method | Path | Purpose / current limitation |
|---|---|---|
| `POST` | `/checks/` | Submit a claim; returns HTTP 202 and `check_id` |
| `GET` | `/checks/{id}/` | Poll your check result |
| `GET` | `/checks/` | Paginated history for the authenticated user |
| `GET` | `/health/` | Database and queue-configuration probe; readiness incomplete |
| `GET` | `/models/` | Stub; live cached catalog integration outstanding |
| `PUT` | `/settings/model/` | Store per-tier model preferences; capability validation outstanding |
| `GET` | `/spend/` | Stub; durable, user-scoped ledger integration outstanding |
| `POST` | `/sources/` | Accept captured page text; trusted-cache isolation outstanding |
| `POST` | `/auth/keys/` | Create a hashed extension API key, returned once |

Shared contracts live in `apps/checks/contracts.py` and the inference types.
Coordinate changes across the backend, inference, evidence and client lanes.

## Checks and contributing

Read [ARCHITECTURE.md](ARCHITECTURE.md), [WORK_CHUNKS.md](WORK_CHUNKS.md) and
[CI_CD.md](CI_CD.md), in that order. Follow [AGENTS.md](AGENTS.md) and the
[delivery plan](DELIVERY_PLAN.md) for ownership and implementation sequencing.

Use feature branches and PRs to `main`. Include regression tests and acceptance
evidence with each fix; keep applied migrations unchanged and add new migrations.

```bash
python -m pip install --require-hashes -r requirements-ci.txt
python -m ruff check .
python -m pytest --disable-socket
npm ci --ignore-scripts
npm run extension:lint
npm --prefix frontend/web ci --ignore-scripts
npm --prefix frontend/web test
```

Run the extension check when changing extension code. Tests must use fixtures,
not live provider or Wikipedia calls. The web `npm test` runs offline API-client
contract tests; these do not establish browser or Firefox runtime acceptance.
Live-model evaluation, Firefox runtime checks, deployment,
restore and load tests are separate release gates.

## Configuration and deployment

See [env.example](env.example) and `config/settings/` for supported settings.
Configure database, allowed hosts, CORS, provider keys and Ollama connectivity for
the actual environment. Keep `.env` and provider secrets out of the extension and
out of Git.

Deployment is unfinished. A supported release needs a supervised web process and
Q2 worker, persistent PostgreSQL, migrations, web/static serving, HTTPS, verified
provider access, monitoring, backups and a tested rollback procedure. A hosted
worker cannot reach a laptop's Ollama through its own `localhost` address.

[CI_CD.md](CI_CD.md) documents the current checks, draft releases and optional
portfolio deployment. Version tags create a draft unsigned extension release
after CI passes. Static portfolio deployment is manual and disabled by default.
The full delivery plan retains the outstanding application release gates.

## Repository map

```text
config/            Django settings, URLs and WSGI/ASGI
apps/checks/       claims, checks, evidence, contracts and worker integration
apps/accounts/     API keys and per-user model preferences
apps/inference/    providers, structured output, fallback, catalog and spending
apps/sources/      Wikipedia discovery, retrieval, transport and evidence packing
frontend/web/      vanilla JavaScript web client
extension/         Firefox MV3 client
tests/             backend and fixture-based regression suite
DELIVERY_PLAN.md   remaining work, ownership, sequencing and release gates
```
