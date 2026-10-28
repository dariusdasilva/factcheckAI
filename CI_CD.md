# CI/CD guide

The initial delivery target is the free employer-facing portfolio described in [PORTFOLIO_PLAN.md](PORTFOLIO_PLAN.md). GitHub Actions verifies code and creates reviewable artifacts; it does not provision paid infrastructure, call inference providers or deploy the unfinished backend.

## Continuous integration

`.github/workflows/ci.yml` runs for pull requests, pushes to `main`, `v*` tags and manual dispatch. Required jobs run without path filters so documentation-only PRs still receive the same final status. Superseded branch/PR runs are cancelled; version-tag runs are not cancelled by a newer run. Job timeouts and seven-day artifact retention keep usage bounded.

| Check | What it proves |
|---|---|
| Backend (sqlite) | Ruff, dependency consistency, Django checks, migration drift/application and pytest with all sockets disabled |
| Backend (postgres) | Same checks against a disposable PostgreSQL 16 service, allowing only loopback network connections during tests |
| Web client checks | JavaScript syntax and eight offline API-client contract tests; npm dependency audit |
| Extension lint and package | Locked web-ext lint with warnings treated as failures, high/critical dependency audit and unsigned ZIP artifact |
| Python dependency audit | Published advisories checked against the hash-locked Python dependency set |
| Workflow validation | Checksum-verified actionlint validates workflow syntax and expressions |
| CI complete | Stable aggregate status that fails if any required job fails, is cancelled or is skipped |

The PostgreSQL service uses disposable CI-only credentials. No production data or provider API keys are used. SQLite tests cannot create sockets; PostgreSQL tests may connect only to `127.0.0.1`. Dependency installation and vulnerability-advisory checks need network access, but application tests must not contact Wikipedia, OpenRouter, Gemini or Ollama. Recorded fixtures and mocks are the source of inference/evidence responses.

Backend test XML and coverage XML are uploaded even on test failure when available. Coverage is reported without inventing an arbitrary pass percentage. These tests do not establish actual multi-worker recovery, inference quality or production readiness; those remain backlog acceptance work.

The web tests exercise the shipped API client through a Node VM with injected storage, timers and fetch fixtures. They verify authentication, polling the returned ID, terminal statuses, unavailable results, errors, history and timeout handling. They are not browser, DOM, accessibility or Firefox runtime acceptance. The previous always-successful placeholder test has been removed.

## Reproducible tooling

Use Python 3.12 and Node 24. JavaScript tooling lives in the root `package.json`/`package-lock.json`; the web client has its own package and lockfile. CI uses `npm ci --ignore-scripts`. Extension commands use the installed, exactly versioned `web-ext` instead of downloading an unspecified version through npx.

`requirements.txt` and `requirements-dev.txt` describe supported dependency ranges. `requirements-ci.txt` records the complete resolved CI environment with hashes; CI installs it with `--require-hashes`. Changes to input requirements must include a reviewed regenerated lock. The lock targets Python 3.12; the Linux CI jobs verify the target runner environment as well as local checks.

To regenerate the Python lock in a disposable Python 3.12 virtual environment:

```bash
python -m pip install pip-tools==7.6.2
pip-compile --strip-extras --allow-unsafe --generate-hashes --output-file requirements-ci.txt requirements-dev.txt
```

Use `--upgrade` deliberately when updating the entire dependency set. Review the diff and rerun all checks; never generate a lock by freezing a personal environment containing unrelated packages or credentials.

To update extension tooling, change its exact version in root `package.json`, run `npm install --package-lock-only --ignore-scripts`, and verify lint, packaging and `npm audit --audit-level=high`. Do not apply `npm audit fix --force` blindly. The current web-ext dependency tree has low-severity advisory exposure through deepmerge; high/critical advisories block CI. Review the low-severity exposure on tooling updates rather than claiming the audit is completely clean.

Dependabot opens monthly grouped Python/npm updates and action updates with small open-PR limits. Review generated lock changes and keep both declared requirements and the resolved lock consistent. No automatic merge is enabled.

## Local checks

Run from a clean checkout with the virtual environment active:

```bash
python -m pip install --require-hashes -r requirements-ci.txt
python -m pip check
python -m ruff check .
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py migrate --noinput
python -m pytest --disable-socket --junitxml=reports/pytest.xml
python -m pip_audit --strict --require-hashes -r requirements-ci.txt
npm ci --ignore-scripts
npm run extension:lint
npm run extension:build
npm audit --audit-level=high
npm --prefix frontend/web ci --ignore-scripts
npm --prefix frontend/web run build
npm --prefix frontend/web test
```

For PostgreSQL tests, set `DATABASE_URL` to a disposable local database and replace `--disable-socket` with `--allow-hosts=127.0.0.1`. Never run the test/migration commands against personal or production data. Test reports are ignored by Git.

## Extension delivery

The ordinary CI job uploads the unsigned ZIP under the `firefox-extension` artifact. This supports code review and temporary development testing; it does not establish signing, AMO approval or runtime acceptance. The unfinished extension must not be advertised as a ready fact-checker while its P0 defects remain.

A pushed `v*` tag runs the complete CI workflow. Only after the aggregate gate succeeds does the draft-release job:

1. Check that the tagged commit belongs to `main` and the tag equals `v` plus `extension/manifest.json`'s version.
2. Download the exact ZIP already linted and built in that run, rather than rebuilding a different artifact.
3. Add `SHA256SUMS.txt` and create a **draft** GitHub Release with an explicit development warning.

For example, manifest version `1.0.0` requires tag `v1.0.0`. Tags are maintainer actions, not part of every feature PR. No release tag is created by this change. If a tag or draft already exists, inspect it rather than deleting or overwriting published artifacts to retry. Publishing the draft requires a separate maintainer decision and the relevant acceptance evidence. A green workflow alone cannot waive P0 blockers.

## Optional free portfolio deployment

`.github/workflows/pages.yml` is manual-only and disabled by default. It publishes **only** the dedicated `portfolio/` directory. It never uploads the repository root, `.env`, database or unfinished `frontend/web/` application.

When a reviewed static showcase exists:

1. Add `portfolio/index.html` and its public assets. Ensure links work beneath the repository's Pages subpath. Label recorded examples, use no provider keys and include an offline-friendly walkthrough.
2. Review every published asset for private data. Test the page with the backend stopped and without an account.
3. In repository Settings, enable Pages with **GitHub Actions** as its source; configure the `github-pages` environment to permit deployment from `main` only.
4. Set repository Actions variable `ENABLE_PORTFOLIO_PAGES` to `true`.
5. Run **Portfolio Pages** from the Actions tab on `main`. The workflow refuses a missing entry page or symlinked source and uploads only the showcase folder.
6. Verify the returned public URL before adding a live-demo link or badge. Disable the variable to stop subsequent workflow deployments; this does not unpublish an existing site. Use Pages settings to unpublish when needed.

This change prepares the workflow only: no portfolio entry page, Pages setting or public deployment has been created. No custom domain is required. The live Django/Q2 backend and a secure Ollama connection remain separate, optional deployment work; GitHub Pages cannot run them.

## Repository safeguards and permissions

Actions are pinned to verified full commit SHAs with version comments. Checkout does not persist credentials. Default workflow permissions are read-only. Only the tag draft-release job gets `contents: write`; only Pages deployment gets `pages: write` and `id-token: write`. Workflows do not use `pull_request_target` to execute PR code and do not expose inference secrets to PRs.

A repository administrator should configure branch protection/rulesets for `main` to require **CI complete**, review approval, resolved conversations and no force pushes. Settings are not changed by a YAML file and are not claimed as configured. Keep secret scanning/push protection enabled where available. Dependency audits report known package advisories; they are not source-code vulnerability scans or secret scans.

Future production deployment must follow [DELIVERY_PLAN.md](DELIVERY_PLAN.md), including persistent state, supervised workers, security controls, backups/restore, real provider outages and rollback. No automatic paid backend deployment is configured.
