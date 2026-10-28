# FactCheckAI delivery plan

Prepared 26 October 2026 for the existing FAI-01–FAI-48 backlog. Planning baseline: repository commit c245c28, clean working tree when checked; live Super Productivity read confirms 48 tasks, all open. This document plans implementation; it does not mark tasks done, change application code, deploy, or create replacement tasks.

## Approved initial target: employer-facing portfolio demo

The owner has selected a portfolio release with a target of zero recurring hosting cost and optional, explicitly capped API spending. Continuous uptime, a paid domain, paid managed infrastructure and continuously hosted Ollama are not initial requirements. See [PORTFOLIO_PLAN.md](PORTFOLIO_PLAN.md) for the initial delivery sequence and acceptance checklist.

**Release profiles:** the initial static showcase is separate from the real application. It may publish screenshots, a walkthrough and visibly labelled recorded examples while the backend is offline. It must not expose unfinished live API paths or distribute an unsafe extension as ready. Any optional hosted live checks require the security, correctness, resource and spending controls for every exposed path. Local setup retains the intended remote/Ollama/fail-state contract.

**How to read the rest of this document:** the 19 packages, M0–M6 schedule, estimates and comprehensive release gates below describe the full intended application/production roadmap. They are retained for future work, not a prerequisite for publishing a static portfolio showcase. Their estimates are not estimates for the smaller portfolio release. All seven P0 tasks remain blockers for the full application release; a static showcase neither waives them nor marks them complete. Existing task priorities and acceptance criteria remain unchanged. Deferred production capabilities stay open and must not be advertised as delivered.

## 1. Recommended approach

Run four coordinated lanes—A backend/integration, B inference, C evidence and D clients—with A maintaining the shared contracts and merge queue. Fix trust and no-fabrication defects immediately, then make attempts/spending/execution durable, complete the API and both clients, and prove the actual deployment before releasing. Tests and documentation develop with each change; the later assurance packages finish coverage rather than start it.

The original 48 tasks remain the system of record. This plan groups them into 19 reviewable work packages; large packages should become several small PRs. Every task has exactly one primary package below, even where preparation and final acceptance span several milestones. Dependencies in the original notes usually describe final acceptance, not a prohibition on starting fixture-based implementation.

**Non-negotiable outcome:** no production path invents a verdict. Evidence insufficiency is an honest `unverified` result from available inference; inference unavailable/invalid is `fail_state` without a verdict or confidence. Preserve `queued | running | ok | fallback | fail_state`, the frozen internal contract, Django/DRF, Django-Q2, polling, OpenRouter primary, Ollama local and Wikipedia-first retrieval. Any new fields are coordinated additive metadata; internal attempt/lease state must not silently rename public status strings.

## 2. Capacity and estimates

Estimates are planning allowances, not commitments. One engineering day means **6 focused hours** of implementation, relevant regression testing and local validation. Package base estimates total **79–122 engineering days**. Reserve a further **25%** for integration, review turnaround, evaluation failures and deployment discovery: approximately **99–153 days**, or **594–918 focused hours**. Review the estimate after the first P0 fixes and the ledger/lease design spike.

A reference team of four contributors each providing 18 focused hours/week has 72 focused hours/week of capacity. Aggregate effort suggests about 9–13 weeks; allow a **10–14 week planning window** because A's migrations/contracts and live acceptance form a serial bottleneck. A four-person team each providing 30 focused hours/week may reach roughly 6–9 weeks; one person at 30 focused hours/week should plan roughly 20–31 weeks before any additional hardware or access delay. These are conditional forecasts, not promised dates. Do not divide work evenly by task count: FAI-21 is much smaller than FAI-06.

The week ranges below overlap intentionally and assume the reference team. Replan after actual availability is known. No calendar due dates or estimates were written to Super Productivity during this planning turn.

## 3. Decisions to record in the first planning session

Decisions marked settled in ARCHITECTURE.md stay settled. Record the following remaining implementation/product choices in short design notes, with owner and decision date:

| Decision | Recommended starting position | Owner | Needed before |
|---|---|---|---|
| Supported launch topology | Initial target decided: free static employer showcase plus documented local application; optional sleeping live demo only after exposed-path acceptance. Hosted production and always-on Ollama remain future profiles. | A + product owner | WP12 deployment acceptance |
| Shared state | PostgreSQL is authoritative for money, reservations, attempts and leases. For breaker/crawl coordination, choose a DB-backed mechanism first unless a managed Redis service is already part of the deployment. LocMem is dev-only convenience, not proof of shared enforcement. Keep Q2's ORM broker. | A + B + C | WP04/06/07/08 implementation |
| Account provision | Retain explicit admin-provisioned access for the first supported release unless public self-registration is required; do not build both paths by default. Define recovery/key lifecycle accordingly. | Product owner + A/D | WP11 account work |
| Billing uncertainty | Preserve reservations for ambiguous paid requests, track reconciliation and operator-wide provider budget separately from per-user caps. Define what the UI calls estimated versus actual. | A + B + account owner | WP06 |
| Time and quota | Track queue wait separately; agree the 90-second processing/deadline boundary and fallback budget. Preserve the current default quota unless a reviewed contract change is approved; start with adaptive polling and result resumption. | A + B + C + D | WP07/11 and schema freeze |
| Models and delivery scope | Verify primary Gemma/Ollama capabilities live; decide whether optional Gemini compatibility is supported in this release. Choose desktop Firefox minimum and whether Android/AMO or temporary sideload is actually in scope. | B/D + product owner | WP09/13 |
| Quality and operation thresholds | Name the model-evaluation acceptance criteria, workload/concurrency, queue/processing SLOs, retention periods and backup RPO/RTO before final evaluation. No accuracy marketing threshold is invented from the small fixture set. | Product owner + A/B/C | WP14/15/16 |
| Release accountability | Name the person who can authorize public release, approve supported-scope changes and execute rollback. | Product owner + A | M6 |

## 4. Ownership and safe parallel work

| Lane | Primary ownership | Early independent work | Shared-file rule |
|---|---|---|---|
| A: backend/integration | checks, accounts, config, migrations, CI, deployment | Baseline/order fix, inactive keys, schema/ledger/lease designs and staging skeleton | A serializes changes to shared models, serializers, routes and tasks.py. |
| B: inference | inference providers/parser/service/catalog/spend internals | Authoritative-label propagation, provider/capability fixtures and breaker tests | B proposes integration fields/signatures; A integrates checks/accounts adapters. |
| C: evidence | sources transport, cache readers, retrieval/packing | Destination-policy fixtures, relevant-section/reference fixtures and provenance contract | Coordinate transport changes as one short sequence; A owns Source/capture migrations. |
| D: clients | frontend/web and extension | Remove randomness, safe history rendering, full selection/configuration and browser harness | Keep one owner per client entry file at a time; integrate lifecycle/settings/accessibility incrementally. |

A single human can occupy several lanes, but then parallelism and the calendar shrink accordingly. If agents assist implementation, give each one a bounded chunk, the relevant contract and acceptance tests; use isolated worktrees for edits, and keep only one writer for a shared integration change. Verify the child has the required tools before delegation. Do not run multiple desktop agents against the same app. A completed or blocked delegated result is not proof until the integration owner verifies it.

Keep WIP at one implementation PR and one review per lane. Use feature branches and PRs to main. Prefer small independently testable commits. Never force-push main, commit secrets or edit applied migrations. Review authentication, spending, prompt/schema and execution contracts closely; a fresh reviewer checks fallback/fail-state and fixture hermeticity before merging affected chunks.

## 5. Milestones and acceptance gates

### M0: Agree contracts and establish a trustworthy baseline

**Reference window:** Week 1; preparation continues alongside implementation.

**Exit gate:** Owners, launch profile and schema drafts recorded; reported history failure reproduced/fixed; meaningful test/CI harness exists. Do not claim every assurance task is complete.

**Main packages active:** WP00, WP12, WP13, WP14, WP15, WP16, WP17, WP18. A package appearing at several milestones has early work and later verification; it is not duplicated effort.

### M1: Remove immediate unsafe behaviour

**Reference window:** Weeks 1–3.

**Exit gate:** Random extension outcomes removed; XSS/inactive keys regressions fixed; capture provenance, citation allowlist and egress policy have failing-then-passing tests. Some P0 runtime work remains open until M2.

**Main packages active:** WP01, WP02, WP03, WP04, WP05. A package appearing at several milestones has early work and later verification; it is not duplicated effort.

### M2: Close every P0 and make execution durable

**Reference window:** Weeks 2–6.

**Exit gate:** All seven P0 tasks satisfy their full acceptance, including real extension API integration, durable spending and atomic recovery. Multi-worker fault tests exercise the critical path; no public release yet.

**Main packages active:** WP05, WP06, WP07, WP09. A package appearing at several milestones has early work and later verification; it is not duplicated effort.

### M3: Deliver a complete backend/evidence vertical slice

**Reference window:** Weeks 4–8.

**Exit gate:** Live catalogs/spend/settings/depth and truthful metadata are integrated; relevant references and context budgets work. Staging serves web/assets and runs Q2/Postgres; fixture-backed vertical slice passes.

**Main packages active:** WP04, WP05, WP08, WP09, WP10, WP12, WP17. A package appearing at several milestones has early work and later verification; it is not duplicated effort.

### M4: Complete the web and extension workflows

**Reference window:** Weeks 6–10.

**Exit gate:** Both clients work against the final APIs, survive refresh/popup closure and quota errors, and show correct states. History/accounts/settings and production serving pass browser/Firefox acceptance.

**Main packages active:** WP10, WP11, WP12, WP13. A package appearing at several milestones has early work and later verification; it is not duplicated effort.

### M5: Prove quality and operational readiness

**Reference window:** Weeks 9–13.

**Exit gate:** Real selected-model evaluations and outage demos, Postgres fault/load evidence, restore/restart/alerts, accessibility and privacy are verified; documentation matches the tested deployment.

**Main packages active:** WP08, WP13, WP14, WP15, WP16, WP17. A package appearing at several milestones has early work and later verification; it is not duplicated effort.

### M6: Publish a release only after the gates pass

**Reference window:** Weeks 12–14; actual timing follows evidence.

**Exit gate:** No open P0 or unmet required P1; P2 dispositions explicit. Release quality checks, package hashes, rollback owner and known limitations recorded; product owner explicitly authorizes launch.

**Main packages active:** WP00, WP17, WP18. A package appearing at several milestones has early work and later verification; it is not duplicated effort.

## 6. Critical paths and useful early starts

**Runtime path:** WP06 durable attempts/reservations → WP07 atomic work claim/recovery/deadlines → WP11 reliable polling/result resumption → WP16 multi-process and load acceptance → WP18 release.

**Trust/quality path:** WP03 capture provenance + WP04 safe egress + WP05 authoritative labels → persisted citations/degradation/context budgets → WP10 relevant references → WP15 quality/adversarial evaluation → WP18 release.

**Delivery path:** WP12 actual web/worker/database/Ollama topology → WP08 readiness + WP14 restore/operations → WP16 staged outage/load tests → WP18 release.

**Catalog path:** WP09 live capabilities → WP05 complete prompt budgeting + WP11 settings → client and model acceptance.

Start the following before their final dependencies are finished:

- Remove the extension's random output immediately; do not wait for API-origin options. FAI-01 stays open until real API integration also passes.
- Fix the FAI-25 timestamp tie-break immediately; pagination/reopen/error acceptance stays open for WP11.
- Draft lease/deadline/billing interfaces together before any one implementation lands; final crash acceptance needs all three.
- Draft OpenAPI examples and client mocks now; finalize FAI-41 only when the implemented additions match both clients.
- Seed browser, worker/Postgres and release-checklist scaffolding now. FAI-33–35 are coverage/completion tasks, not permission to postpone tests.
- Label ground truth and reserve an untouched holdout now. Run final model evaluations after the corrected pipeline exists.
- Apply accessible control/focus patterns during the first UI edits. Final FAI-36 verification happens after workflows stabilize.
- Create CI trigger/release structure and review policy early; only claim FAI-31/47 complete after the real checks protect release/merges.

## 7. Implementation contracts to settle before shared-file edits

1. **Inference context:** internal request context carries claim, trusted bundle labels/items, effective model/depth, remaining processing budget and attempt correlation IDs separately. Untrusted prompt text cannot mint identity. Preserve the frozen InferenceResult, using adjacent context/outcome types for operational metadata.
2. **Result response:** explicitly distinguish gathered evidence from verdict-selected citations. Add bounded rationale/hop comparison, evidence availability and fallback reason where agreed. Unknown/failed/stale values must not masquerade as zero cost or verified content.
3. **Attempt ledger:** unique attempt identity, check/user ownership, model/provider/prices, reservation and usage state, timestamps and safe error code; durable settlement must be idempotent. Treat uncertain provider activity separately from successful final verdict state.
4. **Execution ownership:** atomic claim/lease token and fenced terminal writes. A stale worker must not overwrite a newer owner. Do not promise exactly-once external calls: a crash after transmission can leave an uncertain billed outcome. Choose safe reconciliation/fail-state behaviour explicitly.
5. **Capture/cache trust:** separate user captures from verified shared crawl data. Preserve legacy content but mark unknown provenance; require verification before trusting it. Stale fetch errors do not grant trust.
6. **Deadlines:** budget every stage, including DNS/connect/redirect/body read/extraction, and retain time for persistence. Queue wait is measured separately; the UI can resume a still-pending job instead of inventing fail_state when its own timer expires.
7. **Settings/health:** one configured provider endpoint source, catalog-backed selection policy and distinct liveness/readiness; public health cannot expose another user's models or server keys.

Keep database transactions short and outside network calls. Use transactions/conditional claims and appropriate Postgres locking for state transitions; prove concurrency on PostgreSQL rather than assuming SQLite provides the same locks. If enqueueing after commit, handle enqueue failure with a durable retry/reconciliation path—the callback alone is not an atomic delivery guarantee. [Django transactions](https://docs.djangoproject.com/en/5.2/topics/db/transactions/), [QuerySet locking](https://docs.djangoproject.com/en/5.2/ref/models/querysets/#select-for-update).

The broker retry interval must exceed the worker hard timeout and real task duration to avoid repeat delivery. Do not raise timeouts merely to conceal stuck states. Test the intended OS, especially Windows recovery behaviour. [Django-Q2 configuration](https://django-q2.readthedocs.io/en/master/configure.html).

A Requests read/connect timeout is not a total elapsed-time limit. Total-budget enforcement and a bounded way to end or isolate slow work are separate implementation requirements. [Requests timeouts](https://requests.readthedocs.io/en/latest/user/advanced/#timeouts).

## 8. Work-package implementation briefs

Estimates include package implementation and relevant regression tests; the contingency above covers integration/discovery. Broad acceptance suites in WP13/16 add cross-component proof rather than duplicate every unit test. Within each package, split PRs at the listed step boundaries where that reduces review risk.

### WP00: Reproducible baseline and review controls

**Tasks:** FAI-32, FAI-47. **Accountable lane:** A. **Estimate:** 3–4 engineering days. **Start:** M0; **final gate:** M6.

**Prerequisites:** Start immediately; release safeguards close after real CI gates exist.

**Expected file area:** requirements*.txt, pyproject.toml, .github/, contributor/review guidance.

1. Reproduce the audit baseline and capture the existing history-ordering failure; repair the narrow FAI-25 ordering defect in an early independent PR rather than suppressing the assertion.
2. Resolve and pin the supported Python/Node/tooling environment, document offline fixtures, and create meaningful CI jobs with socket blocking and migration checks.
3. Assign named owners/reviewers, CODEOWNERS where useful, required-check policy and secret/dependency scan triage. Verify actual remote protections only when implemented; finalize FAI-47 after downstream gates exist.

**Required proof:** A clean checkout has a repeatable environment and executable quality gates; required checks genuinely fail when deliberately broken and pass after repair. Record effective branch/release safeguards.

### WP01: Small security regressions with immediate value

**Tasks:** FAI-05, FAI-21. **Accountable lane:** D + A. **Estimate:** 1–2 engineering days. **Start:** M1; **final gate:** M1.

**Prerequisites:** Independent; coordinate CSP/static headers with WP12.

**Expected file area:** frontend/web/app.js, apps/accounts/authentication.py, focused tests.

1. Render history through textContent/DOM construction and constrain navigable URLs; verify sibling sinks without rewriting unrelated UI.
2. Reject inactive users in API-key authentication while retaining revoked/malformed-key behaviour.
3. Introduce the minimal browser regression harness for malicious-claim literal rendering; add inactive-account API tests. Introduce an enforceable CSP alongside compatible asset changes, rather than claiming escaping alone is a CSP.

**Required proof:** Malicious claim markup does not execute in history; inactive-key requests return authentication failure on protected endpoints. Owner-scoped history remains intact.

### WP02: Replace the extension mock path

**Tasks:** FAI-01, FAI-22. **Accountable lane:** D. **Estimate:** 3–5 engineering days. **Start:** M1; **final gate:** M2.

**Prerequisites:** Immediate removal of randomness is independent; API integration uses baseline checks contract.

**Expected file area:** extension/popup.js, options.*, manifest.json, transport test fixtures.

1. First remove generated verdicts from the distributable extension. Until a validated server result exists, display explicit unavailable/pending UI without a verdict or confidence.
2. Add validated API-origin/key configuration, least necessary host permission, full selection storage separate from preview, source context and configuration warnings.
3. Implement authenticated submit-then-poll using fixture cases initially; preserve real claim text, treat permission/key failures accurately, and keep mocks in test code.

**Required proof:** The built extension contains no random verdict path. Full selections reach the configured API; invalid configuration and both-provider outage never produce a verdict. Run lint and focused extension checks.

### WP03: Restore evidence provenance

**Tasks:** FAI-02. **Accountable lane:** A integrates; C adapts fetch. **Estimate:** 3–5 engineering days. **Start:** M1; **final gate:** M2.

**Prerequisites:** Agree capture/cache schema with WP05 and WP07 before migrations.

**Expected file area:** apps/checks/models.py, source_serializers.py, views.py, migrations/, apps/sources/source_fetch.py.

1. Separate user-owned captures from server-fetched shared cache using an explicit provenance/verification boundary.
2. Use additive migrations; label existing unverifiable rows legacy/unknown and require server revalidation before using them as trusted publisher evidence. Preserve submitted content.
3. Make cache lookup and stale-content reuse admit only verified server content. Cover both new-row insertion and overwrite attempts by a second user.

**Required proof:** A two-user test cannot replace publisher-attributed evidence through POST /sources/. Expiry and failed refetch cannot restore trust to an unverified legacy/captured row.

### WP04: Constrain and coordinate all crawler traffic

**Tasks:** FAI-03, FAI-18, FAI-19. **Accountable lane:** C; A configures deployment egress. **Estimate:** 5–8 engineering days. **Start:** M1; **final gate:** M3.

**Prerequisites:** Destination policy first; streaming deadline uses WP07's budget interface.

**Expected file area:** apps/sources/politeness.py, robots.py, citations.py, constants.py, wiki_client.py.

1. Implement one shared outbound policy for both robots and source fetching: canonical HTTP(S) authority, permitted ports, public IPv4/IPv6, connection-time enforcement and bounded explicit redirects. DNS prechecking alone is insufficient.
2. Reapply destination checks and destination-host scheduling at every hop. Coordinate one in-flight request and minimum spacing across independent worker processes with an agreed shared mechanism.
3. Add endpoint-specific MIME/byte guards, real contact UA, maxlag/Retry-After handling, robots status policy, explicit stale/error metadata and session cleanup. Integrate bounded parsing and total elapsed budget.
4. Use fixture servers/adapters for private IP, public-to-private redirects, rebinding, converging redirects, MIME/size errors, robots failures and trickle/invalid PDF responses; confirm network egress on staging.

**Required proof:** No disallowed outbound connection occurs in transport tests; two processes cannot overlap requests to one canonical host. Existing MediaWiki politeness and cache-hit tests continue to pass.

### WP05: Make evidence and verdict identity explicit

**Tasks:** FAI-04, FAI-14, FAI-15, FAI-17. **Accountable lane:** B + C internals; A owns persistence/API. **Estimate:** 6–9 engineering days. **Start:** M1; **final gate:** M3.

**Prerequisites:** Authoritative labels first; persistence needs WP03 schema agreement; full prompt budget uses WP09 capabilities.

**Expected file area:** apps/inference/output.py, providers/, types.py, apps/sources/packer.py, apps/checks/tasks.py and serializers/models.

1. Pass an immutable evidence-ID allowlist separately from rendered claim/source text through every provider adapter and parser. No authoritative evidence means no supported true/false result.
2. Add durable labels, selected-citation relations and bounded structured explanations; distinguish retrieved context from cited support and retain hop disagreement where evidence establishes it.
3. Carry evidence availability, skipped/stale sources and distinct fallback reasons into additive result metadata. Preserve exact terminal status strings and the frozen InferenceResult; use adjacent internal context/outcome types or a coordinated additive API envelope.
4. Budget the entire serialized prompt, instructions/schema and reserved output against the selected model; enforce per-source consumption caps even for legacy/captured content. Reject or truncate context explicitly rather than silently relying on Ollama.

**Required proof:** Claim/snippet/title/URL forged labels are rejected; one cited source among several is persisted and rendered correctly; empty/contradictory bundles behave honestly; boundary-sized prompts fit the actual configured context.

### WP06: Durable spending and auditable inference attempts

**Tasks:** FAI-06, FAI-11, FAI-42. **Accountable lane:** A + B. **Estimate:** 6–9 engineering days. **Start:** M1; **final gate:** M3.

**Prerequisites:** Approve accounting/attempt schema and conservative uncertain-call policy before implementation.

**Expected file area:** apps/inference/spend.py, service.py, provider usage capture; apps/checks/models.py, tasks.py, views.py.

1. Model per-user monthly budget state, reservations and provider attempts with exact monetary arithmetic and immutable price/usage snapshots; define ownership of the shared provider-account cap.
2. Reserve transactionally before the remote call, perform network work outside database locks, and settle idempotently. Record billed invalid output and every attempted provider, not only the final successful one.
3. Treat a lost response or timeout as uncertain billing, retaining a conservative reservation until reconciled; do not automatically refund or blindly retry a potentially billed request. Separate estimated and known actual usage.
4. Expose user-scoped spend/cap/90% warning/fallback reason; use stable safe errors and correlation IDs while redacting keys, internal endpoints and unnecessary claim text.

**Required proof:** Independent workers, cache loss, restart, month rollover and near-cap races cannot reset or double-settle spending. Invalid remote JSON followed by local success still retains the remote attempt; uncertain charges are visible and conservatively accounted for.

### WP07: Recoverable execution and atomic terminal state

**Tasks:** FAI-07, FAI-08, FAI-43. **Accountable lane:** A; B/C implement budget propagation hooks. **Estimate:** 6–9 engineering days. **Start:** M1; **final gate:** M3.

**Prerequisites:** Interfaces start with WP06; final crash safety requires WP05 citation persistence and WP06 attempt accounting.

**Expected file area:** apps/checks/tasks.py, models.py, migrations/, Q_CLUSTER settings, providers and source deadline hooks.

1. Implement an atomic queued-to-running claim with a lease/attempt ownership token. Fence stale workers so a late result cannot overwrite a newer terminal result.
2. Define a 90-second processing budget measured from work claim across evidence, catalog, prompt and inference; track queue wait separately. Set network-stage limits from remaining time, leave terminal-persistence margin, and keep broker retry later than hard worker termination.
3. Add explicit recovery/supervision for worker death, lease expiry and retry exhaustion; do not claim exactly-once external billing. Only retry ambiguous remote work when safe reconciliation/idempotency is established.
4. Commit terminal result, selected citations and audit event consistently. Roll out additive constraints after auditing/backfilling old rows; keep old migrations unchanged.

**Required proof:** Duplicate deliveries yield one live owner; worker kill at each critical boundary leads to recovery or truthful fail_state; stale results are fenced, uncertain spend is not lost, and slow source/model operations cannot strand running checks.

### WP08: Shared provider protection and honest health

**Tasks:** FAI-09, FAI-29. **Accountable lane:** B; A exposes readiness. **Estimate:** 3–5 engineering days. **Start:** M2; **final gate:** M5.

**Prerequisites:** Shared coordination decision, WP09 selected models, WP12 staged workers.

**Expected file area:** apps/inference/service.py, provider availability adapters, apps/checks/views.py, worker heartbeat.

1. Persist breaker counters/cooldown/probe ownership at the correct provider/model scope across jobs and processes; update breaker tests before changing provider orchestration.
2. Separate bounded public liveness from authenticated/cached readiness, selected-model availability and worker heartbeat. Detect local_missing without leaking keys or another user's selections.
3. Use local/cap/provider-failure reasons accurately and prove recovery after three failures and 60-second cooldown; finalize operational verification on the actual staged topology.

**Required proof:** A multi-process test admits one half-open probe; three separate jobs trip the breaker. A stopped worker or missing selected model no longer reports healthy readiness.

### WP09: Live models and capability-aware settings

**Tasks:** FAI-10, FAI-13. **Accountable lane:** B; A exposes API/settings validation. **Estimate:** 3–5 engineering days. **Start:** M2; **final gate:** M3.

**Prerequisites:** Baseline schema from WP17; avoid dependency on client completion.

**Expected file area:** apps/inference/catalog.py, provider capability adapters, checks views/routes, accounts serializers.

1. Replace stub model endpoint with live cached OpenRouter Gemma catalog and configured Ollama installed models; use one configured local endpoint consistently.
2. Normalize and validate prices, include context/output/structured-output capabilities, refresh/stale/unavailable states and honest empty-local guidance.
3. Validate selections against permitted instruction-tuned/installed capabilities with a defined upstream-outage policy; verify primary defaults live. Keep Gemini optional scope explicit and never assume a paid alternative is free.

**Required proof:** Fixture catalogs populate both tabs correctly; unavailable/stale/empty catalogs are distinct; arbitrary unsupported model IDs are rejected or handled under documented stale-cache rules.

### WP10: Complete the two-hop evidence product

**Tasks:** FAI-16, FAI-20. **Accountable lane:** C; A persists request settings; D adds controls. **Estimate:** 4–6 engineering days. **Start:** M2; **final gate:** M4.

**Prerequisites:** WP04 safe transport and WP05 label/provenance contract.

**Expected file area:** apps/sources/article_read.py, wiki_client.py, citations.py, pipeline.py, API depth serializer.

1. Retrieve claim-relevant article sections and real reference markup through the shared transport rather than only lead text and arbitrary external links.
2. Preserve reference-to-article provenance and choose relevant primary sources within the fixed fan-out; test fallback through the real pipeline entry point.
3. Expose validated fast/balanced/deep selection in request/settings, persist the effective depth and pass it through both clients and the worker.

**Required proof:** A decisive fact outside the lead is retrieved; reference fallback works without manually injecting HTML in the test caller; source counts respect 0/3/5 and canonical label rules.

### WP11: Finish client workflows and account lifecycle

**Tasks:** FAI-12, FAI-23, FAI-24, FAI-25, FAI-26. **Accountable lane:** D; A owns account/history APIs. **Estimate:** 6–9 engineering days. **Start:** M1; **final gate:** M4.

**Prerequisites:** Start against agreed fixtures; full acceptance uses WP05/06/07/09 and WP02.

**Expected file area:** frontend/web/api.js and app.js, extension popup/content/options, accounts/checks APIs.

1. Make both clients load/save server settings and actual spend/catalog data; preserve full claims, bind results to check IDs, and acknowledge success only after server confirmation.
2. Implement adaptive polling, cancellation, fetch limits and persisted check IDs; handle quota exhaustion/Retry-After without losing the result. Distinguish transport/auth/validation failures from server inference fail_state.
3. Resume extension work after popup closure, render verdict_enum consistently, show neutral unverified/fail_state and accurate local-mode reasons, and handle lost selections/restricted pages/message acknowledgements.
4. Finish history pagination/result reopening and deterministic timestamp/ID ordering; complete the chosen account provisioning flow, secure session/CSRF behaviour where used, and key listing/revocation/rotation with invalid-token recovery.

**Required proof:** Reload, popup close, logout, parallel requests and nearly exhausted quota cannot show a stale or fabricated verdict. Settings affect the next real check; history remains safe, stable and user-scoped; revoked/inactive credentials fail.

### WP12: Real production serving and worker topology

**Tasks:** FAI-27, FAI-28. **Accountable lane:** A; D verifies assets. **Estimate:** 4–6 engineering days. **Start:** M0; **final gate:** M4.

**Prerequisites:** Scaffold staging immediately; processing acceptance depends on WP07 and safe provider/evidence controls.

**Expected file area:** config/urls.py, settings/prod.py, deployment process definitions, static setup, environment documentation.

1. Choose the laptop demo and intended production topology explicitly, with a documented reachable and protected Ollama endpoint. Hosted localhost is never described as the laptop.
2. Serve root/assets with DEBUG=False, configure same-origin web API behaviour and collectstatic, provision persistent PostgreSQL, supervised web and Q2 processes, and environment/secrets validation.
3. Use expand/backfill/enforce migration rollout, validate proxy/HTTPS configuration and graceful shutdown, then exercise submit-to-completion on staging with worker and database restarts.

**Required proof:** A fresh staged deployment serves the application and processes checks with production settings; restart retains data and recovers work. Remote, local and both-down behaviours are demonstrated on actual intended hosts.

### WP13: Browser, extension and presentation acceptance

**Tasks:** FAI-34, FAI-35, FAI-36, FAI-44. **Accountable lane:** D. **Estimate:** 5–8 engineering days. **Start:** M0; **final gate:** M5.

**Prerequisites:** Harness/design start immediately; closure after WP11 and WP12. P2 visual polish may be explicitly deferred.

**Expected file area:** web browser specs, extension harness/manual checklist, UI HTML/CSS, CI test jobs.

1. Replace placeholder npm tests with deterministic assertions and fixture APIs; add regression tests with each client fix rather than waiting for this package to finish.
2. Cover all status/error/retry/history/settings/credential paths with Playwright and screenshots; lint/build the extension and run the documented real Firefox matrix, including Android only if claimed.
3. Design labels, focus, live regions, keyboard flow, contrast, responsive layouts and reduced-motion behaviour from the first UI change; verify narrow screens, zoom and long URLs.
4. Finish consistent components, neutral status colours and truthful provenance/cost/setup copy using real states. Review actual rendered screens; do not change the selected frontend stack solely for cosmetics.

**Required proof:** Meaningful browser assertions fail on regressions; Firefox smoke includes both-provider outage and popup resume; mobile/keyboard/assistive-tech checks pass, with visual evidence retained.

### WP14: Operational support and data handling

**Tasks:** FAI-30, FAI-37. **Accountable lane:** A + D. **Estimate:** 4–6 engineering days. **Start:** M0; **final gate:** M5.

**Prerequisites:** Define data flow/retention early; verify operations on WP12 deployment and WP06 attempts.

**Expected file area:** logging/metrics configuration, operational docs, backup jobs, privacy/extension consent assets.

1. Choose retention, backup RPO/RTO and alert ownership; map claims/page URLs/account metadata to storage and remote providers. Define what is logged and what is omitted.
2. Add queue-age/stuck-run, fail/fallback, latency and budget alerts with safe correlation IDs; test that an operator can identify an incident without exposed keys or raw private content.
3. Run an actual database restore and rollback rehearsal; finalize truthful privacy/consent documentation and current Mozilla data-transmission declarations before distribution.

**Required proof:** Restore/restart and alert tests have recorded outcomes; retention and recipients match actual behaviour; extension permissions/consent and published privacy copy agree with transmitted data.

### WP15: Evaluation and adversarial evidence

**Tasks:** FAI-38, FAI-39. **Accountable lane:** B + C; human labels independently. **Estimate:** 5–8 engineering days. **Start:** M0; **final gate:** M5.

**Prerequisites:** Ground-truth/adversarial fixtures start now; final runs after WP03/04/05/10.

**Expected file area:** versioned eval dataset, recorded/synthetic fixture metadata, evaluation runner and report.

1. Select a diverse labelled set and source-date ground truth independently of model output; keep a small development set plus separate untouched holdout. At least 20 claims is a smoke floor, not a claim of statistical reliability.
2. Include true/false/unverified, time-sensitive, negated, ambiguous, unsupported, conflicting and malicious-source cases; record capture/sanitization provenance and separate synthetic examples.
3. Run remote and local tiers at each supported evidence depth, measuring retrieval coverage, verdict confusion/abstention, citation correctness and latency. Freeze release thresholds before looking at holdout results.
4. Investigate failures by retrieval/parsing/inference/presentation cause. Keep confidence display-only; if factual quality misses the agreed bar, improve evidence or abstain rather than relax truthfulness.

**Required proof:** Versioned results identify model/prompt/data versions and every failure. No-fabrication/citation-admission regressions pass; product accuracy claims are no broader than supported evaluation evidence.

### WP16: Integration, fault injection and load limits

**Tasks:** FAI-33, FAI-40. **Accountable lane:** A orchestrates; B/C supply fixture services. **Estimate:** 5–8 engineering days. **Start:** M0; **final gate:** M5.

**Prerequisites:** Harness starts now; complete scenario coverage after runtime, crawl and staged topology packages.

**Expected file area:** backend integration suite, PostgreSQL CI job, controlled load scripts/reports.

1. Exercise real Q2 workers and PostgreSQL with fixture-backed provider/crawl services; block external internet in CI but permit explicitly local fixture endpoints for the integration job.
2. Test two worker processes, duplicate deliveries, stale leases, counter resets, spend races and injected kills around reservation/call/settlement/persistence. Use transaction-capable tests rather than SQLite-only lock claims.
3. On controlled staging, measure queue wait separately from processing, p50/p95 latency, memory/model contention, source limits and degraded-mode capacity; test three outage modes and slow responses.
4. Set bounded per-user/global admission and backpressure from measurements, then rerun the target workload. Keep fast PR smoke separate from slower scheduled/manual fault suites so the normal checks remain usable.

**Required proof:** Recorded fault matrix has no fabricated output, duplicate settlement or permanent unowned running work. Load results justify concurrency limits and release SLOs on the actual topology.

### WP17: Stable contracts, documentation and local startup

**Tasks:** FAI-41, FAI-45, FAI-46. **Accountable lane:** A integrates; every lane supplies examples. **Estimate:** 4–6 engineering days. **Start:** M0; **final gate:** M6.

**Prerequisites:** Draft API fixtures now; finalize after catalog/spend/evidence/depth and deployment contracts stabilize. Final release-command documentation and optional startup verification close at M6 after tag-release evidence. P2 startup tooling can be deferred.

**Expected file area:** OpenAPI/contract fixtures, README/env.example/client docs, optional dev orchestration.

1. Publish the current baseline schema first, then review additive evidence/fallback/model/spend/depth metadata together; preserve terminal status strings and canonical public field names.
2. Keep schema/example fixtures synchronized with implementation and run consumer contracts for both clients; define semantics for unverified, fail_state, queued/running, transport errors and quota responses.
3. Update setup, PowerShell/POSIX commands, account/key provisioning, models, worker launch, environment variables and known limitations as PRs land. Finalize after production commands have actually been exercised.
4. Provide a repeatable local start/stop flow or optional orchestration, with no embedded credentials and visibly separated fixture mode. Verify a clean-machine walkthrough.

**Required proof:** Contract examples match real responses; a new developer follows the documented setup and completes a fixture-backed check. Real deployment commands, supported hardware assumptions and troubleshooting are recorded accurately.

### WP18: Release automation and evidence-backed handoff

**Tasks:** FAI-31, FAI-48. **Accountable lane:** A release owner; all lanes sign off. **Estimate:** 3–4 engineering days. **Start:** M0; **final gate:** M6.

**Prerequisites:** Checklist/workflow skeleton start now; publishing requires all mandatory gates and explicit P2 decisions.

**Expected file area:** .github/workflows/, release checklist, artifact manifests, staged acceptance evidence.

1. Create the acceptance checklist before implementation and repair tag-trigger/permission structure early; keep publishing disabled or controlled until real backend/client gates are enforced.
2. Run full staged acceptance with actual selected models: normal remote, local fallback, both-down, no evidence, quota, cap, restart, restore and browser workflows. Record versions, timings, results and known limitations.
3. Resolve every mandatory task against evidence, close P0 only after its acceptance passes, and require explicit owner decisions for P2 deferrals. Recheck original six security findings and the random-verdict defect against their regressions.
4. Produce and verify the extension ZIP and backend release revision, artifact hashes, release notes, rollback/alert ownership and distribution route. A product owner authorizes public launch; do not infer launch authorization from planning.

**Required proof:** No unresolved P0; every P1 acceptance is satisfied for the agreed supported product. A knowingly incomplete required feature changes the declared product scope and release claim, never silently becomes done. Release gates, real outage demonstrations and restore evidence are attached.

## 9. First merge queue and first-week work

These are small review units, not a command to wait for every earlier PR before starting independent work. The first mitigation PR for a task may not finish its full acceptance.

| Initial PR | Concrete change | Tasks advanced | Proof before merge |
|---|---|---|---|
| 00 | Reproduce/fix stable history ordering, capture baseline and pin the minimum repeatable tooling | 25 (partial), 32/33 (bootstrap) | Equal timestamps sort deterministically; existing full suite is green, not suppressed. |
| 01 | Remove random extension verdicts immediately, then add real configured-origin submit/poll in the next bounded slice | 01, 22 | No generated verdict in shipped code; transport fixtures and extension lint. |
| 02 | Safe history DOM construction with malicious-text regression | 05, 34 (harness) | Claim markup displays literally and cannot execute. |
| 03 | Deny inactive-account API keys | 21 | Active/revoked/inactive/malformed cases pass; ownership unchanged. |
| 04 | Add capture provenance separation and adapt cache consumers | 02 | Two-user insertion/overwrite/expiry and legacy-unknown cases cannot poison trusted evidence. |
| 05 | Thread authoritative evidence IDs through each provider/parser | 04 | Forged prompt labels rejected; genuine labels and fail-state fallback still pass. |
| 06 | Shared destination policy for robots/source/redirects | 03; 18/19 begin | Connection-time destination tests pass; final deployment egress proof stays open. |
| 07 | Add reviewed attempt/reservation/lease/citation schema via compatible migrations | 06/07/14/43 (foundation) | Empty and representative existing DBs migrate; old rows have explicit treatment. |
| 08 | Implement transactional reservation and idempotent attempt settlement | 06/11/42 | Near-cap multi-process races, invalid paid response and uncertain timeout cases are accounted for. |
| 09 | Implement atomic work ownership, fencing and recovery with propagated deadline | 07/08/43 | Duplicate delivery, kill/restart, stale writer and trickle cases terminate/recover honestly. |

Start the ledger/lease design during PRs 00–06; it is the critical path, not a late follow-up. C's schema proposals and B's attempt fields enter A's migration queue together. Never let independently generated migration numbers silently overwrite one another.

**Illustrative first-week capacity allocation, four people × 18 focused hours:**

| Lane | Planned focus | Hours |
|---|---|---|
| A | Baseline/order fix 6; inactive-key fix 2; durable schema/lease decisions 7; review/integration 3 | 18 |
| B | Authoritative citation context/parser work 10; spend-attempt design with A 4; model fixtures 4 | 18 |
| C | Capture/cache migration and consumer contract 8; outbound-policy/redirect fixtures 8; review 2 | 18 |
| D | Remove randomness and safe history rendering 9; browser/extension fixture harness 4; API-origin/full-selection slice 5 | 18 |

This is a starting allocation, not a guarantee those packages finish in one week. If estimates diverge, preserve security boundaries and scope the next PR smaller; do not declare partial tasks done. Ground-truth selection, staging access and owner decisions should be arranged during this week so they do not block later acceptance.

## 10. Testing and completion policy

For every relevant code PR:

- Write a regression demonstrating the real defect or contract before the fix. Provider/orchestration changes update circuit-breaker tests first.
- Run `ruff check .` and `pytest` before claiming done. Enforce hermetic external networking in CI; integration jobs may allow explicitly controlled local fixture services.
- When extension files change, run `npx web-ext lint --source-dir=extension`; the release job also builds the artifact with pinned tooling.
- With model changes, add append-only migrations and run migration-drift/application checks on PostgreSQL, including representative legacy data.
- With clients/contracts, run the meaningful browser/consumer fixtures for all affected statuses. Small cosmetic edits need appropriate visual review rather than implementation-mirroring tests.
- A reviewer checks no-fabrication, user isolation, evidence identity, money/attempt handling, and retry/fixture assumptions where affected. The integration owner runs required checks themselves rather than accepting an agent's claim.

Use separate acceptance layers:

| Layer | Covers | Can prove | Cannot prove |
|---|---|---|---|
| Fast offline tests | Schema/parser/serializers, safe DOM and provider/crawl fixtures | Deterministic logic and regressions | Live factual quality or deployed connectivity |
| Postgres + real worker fixtures | Process coordination, leases, spend, queues, migrations | Cross-worker/fault behaviour under the tested setup | Provider billing certainty after an unobserved transmission |
| Browser/Firefox checks | Real API field names, lifecycle, permissions, UI/accessibility | Correct client experience in tested browsers | Whether the model's verdict is factually right |
| Staged actual-model evaluation | Chosen models, retrieval, outage/fallback, resource limits | Measured quality/latency on the labelled set and actual topology | Broad statistical reliability from only 20 claims |
| Operational rehearsal | Restore, rollout, rollback, alerts and shutdown | Recovery procedure and measured RPO/RTO | Future availability without monitoring/ownership |

A task is done only when its original acceptance criteria and the matching package proof are met, PR merged with green required checks, documentation/fixtures updated, and verification evidence attached. The full 48-item state must be checked before task completion changes; do not use stale delegated status. This planning turn does not mutate those tasks.

## 11. Release evidence and go/no-go rules

FAI-48 should contain a checklist referencing these records:

1. Fixed and regression-verified seven P0 issues and all six security findings, with affected paths and PR/revision references. No P0 waiver.
2. All supported P1 features and controls meet acceptance. If a P1 is deliberately removed from the product, record an explicit product-scope decision and revise the advertised release; it remains unsatisfied for the original full scope.
3. Real chosen-model remote success, forced remote failure/local success, both-provider failure with neutral clients, no-evidence unverified, cap/429 recovery, cold-start limitations and complete citation provenance.
4. Multi-worker/Postgres duplicate, crash, timeout, stale-write and spend reconciliation results; no permanent unattended running records.
5. Web/Firefox/permission/popup-resume and accessibility evidence; actual installable artifact with no production mocks.
6. Evaluation dataset/model/prompt/version report, holdout outcomes, failure analysis and agreed performance/resource thresholds. Confidence remains display-only.
7. Tested environment/process topology, backup restore, restart, rollback, safe logs and operator alert ownership.
8. Explicit P2 decisions for FAI-44 and FAI-46. They are included in this full plan but can be deferred from a narrower first release without hiding them.
9. Release commit, dependency resolution, migration sequence, package hashes, release notes, privacy/retention/extension consent and supported-platform statement.
10. Named product-owner launch authorization and named operator on duty. Planning, a green unit suite or a successful lint run is not public-launch approval.

## 12. Risks and how to keep them from delaying everything

| Risk | Early signal | Response |
|---|---|---|
| A becomes the bottleneck | Several lanes await tasks.py/model/serializer changes | Agree interfaces first; serial migration queue; reserve A review capacity; other lanes use frozen fixtures. |
| Remote retry charges twice | Timeout after request transmission with unknown usage | Durable attempt IDs and conservative reservation; reconcile rather than automatically refund/retry. |
| Existing cache data has no provenance | Old fetched rows cannot distinguish user captures | Preserve as unknown and re-fetch before trust; do not label it verified through migration. |
| Passing SQLite tests hides races | Process tests only use dev database | Add PostgreSQL transactions/multi-process fixture jobs before concurrency acceptance. |
| Model/hardware cannot meet budget | Early real smoke check exceeds processing window | Benchmark early, warm intended model, adjust retrieval/admission within settled limits; fail honestly when unavailable. |
| Hosted worker cannot reach laptop | Local API works but staged fallback fails | Decide actual secure topology in M0 and test it before UI completion. |
| Context truncation weakens evidence | Full rendered prompt exceeds selected context | Capability-aware total budgeting with output reserve and explicit truncation order. |
| Live evaluation disappoints | Correct JSON but poor ground-truth/citation outcomes | Separate retrieval errors from inference; improve evidence or abstain; freeze thresholds before holdout. |
| CI becomes slow or fake-green | Placeholder scripts, skipped assertions, long unbounded suites | Genuine fast smoke on every PR; bounded larger suites separately; do not replace assertions with success output. |
| Agent retries duplicate completed work | Child status conflicts with live application state | Read current state, stop stale work, one UI owner; require explicit tool capability before delegation. |

## 13. Task-to-package coverage

Every existing task appears once in this mapping. Early partial PRs do not change its primary package or imply completion. The target gate below applies to the individual task; a package may remain open for its other tasks after an individual task is accepted. In particular, FAI-06/07 close at M2 while their broader ledger/deadline packages continue through M3.

| Existing task | Work | Package | Earliest work / task target gate |
|---|---|---|---|
| FAI-01 | Remove random extension verdicts and call the real checks API | WP02 | M1 / M2 |
| FAI-02 | Separate user captures from trusted shared source cache | WP03 | M1 / M2 |
| FAI-03 | Block private-network crawl destinations and unsafe redirects | WP04 | M1 / M2 |
| FAI-04 | Validate citations using authoritative bundle IDs | WP05 | M1 / M2 |
| FAI-05 | Render history claims as safe text | WP01 | M1 / M1 |
| FAI-06 | Make spend reservations durable across workers and restarts | WP06 | M1 / M2 |
| FAI-07 | Atomically claim queued checks and recover interrupted runs | WP07 | M1 / M2 |
| FAI-08 | Enforce a complete check deadline and bound outstanding calls | WP07 | M1 / M3 |
| FAI-09 | Share circuit breaker state across checks and workers | WP08 | M2 / M3 |
| FAI-10 | Replace model-catalog API stub with live cached catalogs | WP09 | M2 / M3 |
| FAI-11 | Replace spend API stub with user-scoped ledger totals | WP06 | M1 / M3 |
| FAI-12 | Wire both model/settings screens to backend preferences | WP11 | M1 / M4 |
| FAI-13 | Validate model selections and provider capabilities | WP09 | M2 / M3 |
| FAI-14 | Persist verdict-selected citations and evidence explanations | WP05 | M1 / M3 |
| FAI-15 | Carry evidence outages and skipped sources into results | WP05 | M1 / M3 |
| FAI-16 | Retrieve relevant article sections and actual references | WP10 | M2 / M4 |
| FAI-17 | Budget the entire rendered prompt against selected model context | WP05 | M1 / M3 |
| FAI-18 | Enforce crawl politeness across processes and redirect hosts | WP04 | M1 / M3 |
| FAI-19 | Harden crawl retry, robots, MIME and stale-cache policies | WP04 | M1 / M3 |
| FAI-20 | Expose fast/balanced/deep evidence depth end to end | WP10 | M2 / M4 |
| FAI-21 | Reject API keys belonging to inactive users | WP01 | M1 / M1 |
| FAI-22 | Configure extension API origin, key and full claim capture | WP02 | M1 / M2 |
| FAI-23 | Implement extension status rendering and resumable check lifecycle | WP11 | M1 / M4 |
| FAI-24 | Make web polling recoverable within the API quota | WP11 | M1 / M4 |
| FAI-25 | Fix deterministic history ordering and complete history navigation | WP11 | M1 / M4 |
| FAI-26 | Finish account onboarding, logout and API-key lifecycle | WP11 | M1 / M4 |
| FAI-27 | Serve the production web application and assets | WP12 | M0 / M3 |
| FAI-28 | Provide a complete production deployment and fallback topology | WP12 | M0 / M4 |
| FAI-29 | Report real readiness and selected-model availability | WP08 | M2 / M5 |
| FAI-30 | Add monitoring, backup restore and incident runbooks | WP14 | M0 / M5 |
| FAI-31 | Repair tag release triggers and package gates | WP18 | M0 / M6 |
| FAI-32 | Lock dependencies and add vulnerability/secret scanning | WP00 | M0 / M1 |
| FAI-33 | Test actual queue integration and production contracts offline | WP16 | M0 / M5 |
| FAI-34 | Replace placeholder web tests with hermetic browser acceptance | WP13 | M0 / M4 |
| FAI-35 | Verify Firefox extension behaviour and release package | WP13 | M0 / M4 |
| FAI-36 | Complete accessibility and responsive layouts | WP13 | M0 / M5 |
| FAI-37 | Document privacy and correct extension data-consent declaration | WP14 | M0 / M5 |
| FAI-38 | Build an independently labelled fact-check evaluation set | WP15 | M0 / M5 |
| FAI-39 | Add adversarial evidence and abstention evaluation | WP15 | M0 / M5 |
| FAI-40 | Load-test outage paths and enforce resource budgets | WP16 | M0 / M5 |
| FAI-41 | Publish versioned API schema and cross-client contract tests | WP17 | M0 / M4 |
| FAI-42 | Redact errors and retain auditable attempt metadata | WP06 | M1 / M3 |
| FAI-43 | Enforce database result invariants and atomic persistence | WP07 | M1 / M3 |
| FAI-44 | Polish the web and extension experience for release | WP13 | M0 / M5 |
| FAI-45 | Refresh setup documentation and environment examples | WP17 | M0 / M6 |
| FAI-46 | Provide reproducible local development startup | WP17 | M0 / M6 |
| FAI-47 | Define repository review and release safeguards | WP00 | M0 / M6 |
| FAI-48 | Run staged release acceptance and record sign-off evidence | WP18 | M0 / M6 |

## 14. Sources and verification scope

The primary inputs are the current ARCHITECTURE.md, WORK_CHUNKS.md, CI_CD.md and audited 48-task backlog (the original audit report is retained separately; all task mappings and implementation briefs are included in this plan). One independent planning reviewer checked sequencing, ownership and acceptance gaps; no new security scan was run. Current-source checks here only confirmed the baseline revision/clean tree and live task state. The previous 165-pass/1-fail result is historical audit evidence, not a fresh run during planning.

Current implementation guidance was checked against [Django transactions](https://docs.djangoproject.com/en/5.2/topics/db/transactions/), [Django row locking](https://docs.djangoproject.com/en/5.2/ref/models/querysets/#select-for-update), [Django-Q2 timeout/retry configuration](https://django-q2.readthedocs.io/en/master/configure.html) and [Requests elapsed-time limitations](https://requests.readthedocs.io/en/latest/user/advanced/#timeouts). These sources support the proposed transaction/concurrency/deadline test strategy; the actual architecture and acceptance decisions still need implementation evidence.

The plan and package estimates are proposals. No application fixes, PRs, migrations, deployments, task dates, task completion changes or extra Super Productivity tasks were made in this planning turn.
