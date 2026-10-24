# extension/ — Chunk D (Firefox MV3 web extension)

Placeholder. This folder is the home of the Firefox extension (D3/D4/D5 in `WORK_CHUNKS.md`):

- **D3** — `manifest.json` (MV3), popup, selection capture, API-key options options page
- **D4** — same polling as the web app + page badge/overlay, incl. a **neutral fail-state badge**
- **D5** — options: model pickers + spend readout, same UI contract as the web app

Hard rules (from `AGENTS.md` §5, Chunk D): the extension holds **zero secrets and zero business
logic**. Its config is just the API URL + the user's key in `browser.storage`, and it talks to the
same `/api/v1/` endpoints as the web app.

> **CI note:** the `extension` job in `.github/workflows/ci.yml` switches on as soon as
> `manifest.json` appears here, with `web-ext lint --warnings-as-errors` — a single warning fails
> CI. Verify locally before committing any manifest: `npx web-ext lint --source-dir=extension`.
