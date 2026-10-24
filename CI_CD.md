# CI/CD Guide (hackathon edition)

## CI — GitHub Actions (`.github/workflows/ci.yml`, already in repo)

Runs automatically on every push to `main` and every pull request:

| Job | What it does | Owner |
|---|---|---|
| `backend` | ruff lint + pytest over `apps/`, `config/`, `tests/` | A (guards B & C's test suites too) |
| `web` | `npm ci && npm run build && npm test` when `frontend/web/package.json` exists | D |
| `extension` | `web-ext lint` + `web-ext build` when `extension/manifest.json` exists | D |
| `release` | on a `v*` tag only: packages the `.zip` and publishes a GitHub Release | A |

**Rules of the road (from WORK_CHUNKS.md):**
- No test performs a live API call. Chunk B uses recorded OpenRouter responses; Chunk C records real Wikipedia HTTP responses once and replays them (fixtures in `tests/`). CI must stay hermetic.
- Fix CI redness before merging. Nobody merges with a red `main` — that's the one rule that makes CI worth having at a hackathon.
- Rule-of-thumb wall-clock budget: each job should finish in < 3 min. If CI takes longer than doing the change, people skip it — keep it fast.

## CD — two parts, both "click-to-deploy"

### 1. Firefox extension (automated in the workflow)
When you tag a version (`git tag v0.1.0 && git push --tags`), the `release` job builds the signed-free `.zip` and attaches it to a GitHub Release.
- For the **hackathon demo/grading**, that zip is what you submit or sideload via `about:debugging#/runtime/this-firefox` → *Load Temporary Add-on*.
- Releasing on AMO (Mozilla Add-ons) requires an account + review — do it *after* the hackathon, not during.

### 2. Django backend (recommended free-tier stack)
| Piece | Suggested service | Why |
|---|---|---|
| Django app | **Render** free web service | free, Postgres available in-platform, deploy-on-push via GitHub |
| Postgres | Render free tier (or Neon/Supabase if Render's is unavailable) | avoids SQLite-on-disk-loss on redeploys |
| Redis (queue/cache) | skip for the demo — Django-Q2/thread runner + LocMemCache is enough on one dyno | free Redis tiers are flaky; don't risk demo day |
| Ollama (local tier) | **stays on the demo laptop** — do NOT expect a free container host to run 6 GB models. The fallback chain demo: API down → Ollama on the laptop running the Django instance | this is the intended architecture anyway |

Deployment checklist on Render: new Web Service ← your repo; build = `pip install -r requirements.txt`; start = `python manage.py migrate && gunicorn config.wsgi` (add `gunicorn` to requirements at deploy time); env vars `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=0`, `OPENROUTER_API_KEY`. Run `python manage.py collectstatic --noinput` if you serve the SPA through Django.

**During the hackathon:** CI on push is usually enough; set up the Render deploy once the demo backend works locally (≈ after week-long milestone 3-equivalent), not before. A broken deploy is worse than no deploy on deadline day.

## Quick reference

```bash
# tag a release (packages the extension zip automatically)
git tag v0.1.0 && git push origin main --tags

# see CI status without the website
# (needs gh CLI or just open the Actions tab)
```
