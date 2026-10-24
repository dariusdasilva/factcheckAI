# AGENTS.md — Instructions for AI coding agents working on FactCheckAI

This repo is built by human students *and* AI agents working side by side. If you are an AI agent (OpenCode, Claude Code, Copilot Workspace, a scheduled bot, or anything reading this file), these rules are binding.

**Start every session by reading, in this order:**
1. `ARCHITECTURE.md` — the full system design (decisions marked "decided" are settled; don't relitigate them)
2. `WORK_CHUNKS.md` — the 4 work packages (A backend, B inference, C evidence, D clients) and their acceptance tests
3. `CI_CD.md` — pipelines and deploy rules

---

## 1. Repo facts

- **Stack:** Python 3.12 · Django 5 + DRF · JavaScript (web app + MV3 Firefox extension) · Gemma via OpenRouter API (remote tier) and Ollama `gemma4:e4b-it-qat` (local tier)
- **Local dev:** `python -m venv .venv && source .venv/bin/activate && pip install -r requirements-dev.txt`
- **Run all quality checks before claiming done:**
  ```bash
  ruff check .
  pytest
  ```
- **Web/extension checks (Chunk D):** `npx web-ext lint --source-dir=extension` after touching anything under `extension/`.
- **Git:** work on feature branches, PRs to `main`; never force-push `main`; never commit secrets (`.env` is gitignored); delete your remote branch after merge.

## 2. The fail-state law (non-negotiable across all code)

The system **never fabricates a verdict**. When inference is unavailable, responses carry `"status": "fail_state"` and the UI shows a degradation banner — never a made-up answer with a plausible shape. Every agent touching anything between the claim input and the verdict output must preserve this property. It is tested; if your change breaks the fail-state test, the change does not merge.

## 3. Using subagents (delegation patterns that work here)

Subagents are useful for the parallel shape of this project. Proven patterns, and the anti-patterns to avoid:

**Patterns:**
- **One chunk per human/agent pair.** Give a subagent exactly one chunk's scope, the relevant `WORK_CHUNKS.md` section pasted *into the prompt* (subagents don't share your context — paste, don't reference), the repo path, and the chunk's acceptance tests as the definition of done.
- **Explore first.** For "where does X live / how does Y work" questions, spawn a lightweight *explore* subagent, not a coding one. Reads are cheap and parallel; edits are not.
- **Background for independent, long tasks only** (e.g. "record Wikipedia fixtures for the 20 eval claims" while the main session works the backend). If a second task would read files the first task writes, do *not* background it.
- **Reviewer role.** Before merging a chunk's PR, a fresh subagent reads `ARCHITECTURE.md` §2.2 (fallback chain) + the diff and reports contract violations (status strings, fail-state law, fixture-hermeticity). A separate session reviewing is worth as much as a second pair of eyes.
- **Seed new teammates' context.** Hand each chunk's subagent prompt to the corresponding human too — identical context, identical expected tests. Symmetry between agent and human work is what keeps PR reviews fair.

**Anti-patterns (these burn hackathon hours, ignore none of them):**
- ❌ Backgrounding edits that touch the same app as the main session (silent file clobbering).
- ❌ Subagent prompts without the acceptance tests — you get code that "compiles" and misses the point.
- ❌ Letting subagents run `pytest` with network access assumptions (tests are hermetic — fixtures only).
- ❌ Accepting subagent output without running `ruff check . && pytest` yourself. Trust, then verify.

## 4. Gemma 4 best practices (well-known, apply to BOTH tiers)

These are the consensus practices for instruction-tuned Gemma models; they apply identically to OpenRouter-hosted and Ollama-local runs because it is the same model family. Our prompt code lives in `apps/inference/` — keep it in one place (templates module), referenced by both providers.

1. **Always use `-it` (instruction-tuned) variants.** Base pretrained models complete text instead of following instructions. Our API default is `gemma-4-26b-a4b-it*`; our local default is `gemma4:e4b-it-qat` (QAT preserves quality at 3× less memory — see ARCHITECTURE.md §3.1).
2. **Structured output or nothing.** Fact-checking output is parsed by `pydantic`. Ask for **strict JSON with an explicit schema** in the prompt, one example *moved away from the end of the prompt* (to avoid copy-of-example bias), and `response_format={"type":"json_object"}` where the runtime supports it. Never parse free prose.
3. **Low temperature for verdicts.** Verdicts are classification, not creativity: `temperature=0.2–0.4`, `top_p=0.9`, `top_k=40`, and a **fixed `seed`** for reproducibility in tests. Adjust creativity only if we later summarise prose for users.
4. 4. **Give it a role and a refusal shape.** System prompt: "You are a fact-checking assistant. You only judge the given claim using the given evidence ids. If evidence is insufficient, output VERDICT=unverified." Refusals must be a *valid* JSON verdict — never a chat apology we have to regex out.
5. **Evidence ids, not vibes.** Every supporting/refuting line must cite `[W#]`/`[S#]` labels we supplied. Reject (in the pydantic layer) any citation to an id not in the bundle — that is the model hallucinating a source, which is the one failure mode worse than "unverified".
6. **Never ask the model for URLs or dates.** Gemma cannot browse and will confidently invent plausible-looking URLs. All URLs come from our Wikipedia pipeline; the model only chooses among them.
7. **Output budget discipline.** Set `max_output_tokens` explicitly (512 default). Unbounded generation on the local tier can pin the laptop CPU for minutes and starves the 90 s latency cut-off (§2.2).
8. **Ollama-specific: set `num_ctx` in every request.** Ollama defaults to a small context window and *silently truncates* long prompts — your evidence bundle gets cut without an error. Explicitly request `num_ctx: 8192–16384` (e4b fits it) in options, and keep `keep_alive` set so the model stays warm between checks during a demo.
9. **Don't trust the confidence number.** Gemma's self-reported confidence is directionally useful, not calibrated. Treat it as display-only; never gate logic (e.g. "publish if confidence > 0.8") on it without an evaluation set (§9 Q3) showing it means something.
10. **Knowledge-cutoff humility.** Gemma knows *nothing* current; every "recent events" claim must come from our evidence, not memory. If the evidence bundle is empty, the model's job is `unverified`, full stop.

## 5. Chunk-specific agent notes

- **Chunk A:** migrations are append-only history — never edit an applied migration; generate a new one. Settings live in `config/settings/` split files.
- **Chunk B:** every provider change updates the circuit-breaker tests first. Model catalog is *always* rendered from the live OpenRouter/Ollama endpoints (with cache) — never hardcode model lists from a snapshot table.
- **Chunk C:** politeness limits (§3.2) are not optional performance tweaks; they're a condition of being allowed to talk to Wikipedia's API at all. Any new fetch path goes through the shared rate-limited HTTP session.
- **Chunk D:** the extension holds zero secrets and zero business logic. Config = API URL + user key in `browser.storage`. Fail-state UI = neutral badge, guaranteed by the shared status enum with B.

## 6. Using Gemma 4 to WRITE this project's code (developer assistant, not the product engine)

§4 is about Gemma inside the product. This section is about using Gemma (via OpenRouter, or locally in a chat tab) as a code generator during the hackathon. Gemma 4 is a capable small/mid model, not a frontier agent — work *with* its grain:

1. **Scope one task per prompt.** One model/function/serializer/file at a time. "Build the checks app" produces plausible-sounding soup; "write `apps/checks/serializers.py` with `CheckRunSerializer` per this fields list" produces usable code. Long-horizon coherence is where small models degrade first.
2. **Give it the surrounding code, not the repo.** Gemma can't see your repo (unless your harness feeds files). Paste the relevant context *into the prompt*: the model fields, an existing viewset to imitate, the version line (`Django 5.2, DRF 3.15, Python 3.12`) — otherwise it happily writes Django 2.x idioms and invents package APIs that don't exist.
3. **TDD loop works best with small models.** Paste the failing test → ask for the implementation → run `pytest` yourself → paste the traceback back for the fix. Small models converge fast when the test is the ground truth, and you don't get clever-but-wrong structure.
4. **Humans write the contract code, Gemma drafts the boilerplate.** Good delegation: CRUD viewsets, admin registration, JS fetch wrappers, form/table scaffolds, migration commands, docstrings, fixture JSON. Human-written and closely reviewed: prompt templates (§4 — that's literally the product), the circuit breaker, the pydantic schemas, the spend/cost logic (money), and the CSRF/auth wiring (security). A boilerplate bug is annoying; a contract bug silently breaks the fallback chain.
5. **Ask for complete files or complete diffs,** never "just the changed section, keep the rest in mind" — you get hallucinated ellipses (`# ... unchanged ...`) that a teammate pastes and breaks. Specify imports explicitly in the request.
6. **After every generated block:** `ruff check . && pytest`, plus your own read. Never merge generated code on the model's word alone — same rule as §3's subagent policy, one standard for every author.
7. **Pin the coding temperature around 0.4–0.6** (slightly higher than verdicts' 0.2–0.4 is fine; creativity helps naming/hardcode-free structure, but not much more). Fixed `seed` when you want a stable second attempt to compare against the first.
8. **Don't use the `-qat` local e4b for writing code** unless desperate — it's tuned for laptop inference quality of *verdicts*, not code tasks; for coding, the free OpenRouter tier's `gemma-4-31b-it:free` (or `12b` if your machine holds it) is materially better at following your code-related instructions.
9. **Regenerate rather than argue.** If a small model's output is subtly wrong twice, restate the task with narrower scope or paste in the exact test — three explain-fix rounds usually cost more than one clean restate with better constraints.
10. **Keep friendly prompt templates for codegen in version control** (`prompts/` dir is fine) so the whole team shares agreed prompts instead of each retyping — consistency across your 4 developers beats everyone having private prompt stashes.
