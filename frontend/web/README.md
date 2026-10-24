# frontend/web — Chunk D (web app)

Placeholder. This folder is the home of the web application client (D1/D2/D5 in `WORK_CHUNKS.md`):

- **D1** — auth (session login), claim submit form, result render, history
- **D2** — polling progress + "local mode" / "degraded" banners — fail state is a **banner**, never a fabricated verdict
- **D5** — settings: model pickers (API tab with costs, local tab installed-only) + spend readout (from `/api/v1/models/` and `/api/v1/spend/`)

Everything talks to the Django REST API `/api/v1/` (see `ARCHITECTURE.md` §3). Until Chunk A's endpoints are real, we build against a **static JSON mock per §2.2** — mocked first is the rule for this chunk.

> **CI note:** the `web` job in `.github/workflows/ci.yml` switches on as soon as `package.json`
> appears in this folder (runs `npm ci` + build + test). Do **not** add `package.json` until the
> project has a real lockfile and a green `npm test` — otherwise CI goes red for everyone.
