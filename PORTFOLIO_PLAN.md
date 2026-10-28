# Employer-facing portfolio delivery plan

## Goal and budget

Make FactCheckAI easy for an employer to understand and assess, even when the backend is offline. The initial target is zero recurring hosting cost. Small paid inference usage is optional; choose an explicit spending ceiling before enabling it. No paid infrastructure or domain purchase is authorized by this plan.

Use a provider-supplied public address first. Select a free static host when implementation begins, checking its current terms and limits. Keep the showcase portable HTML/CSS/JavaScript. Free hosting availability is not an uptime guarantee.

## 1. Publish a useful static showcase

Owner: D, with A/B/C reviewing the technical claims.

- Introduce the problem, intended users, technical stack and each contributor's work.
- Provide three clear actions: Try the demo, Watch the walkthrough, View the code.
- Show representative screenshots and a short recorded walkthrough of the real local application; fix the demonstrated path before recording it.
- Explain the evidence pipeline, fallback chain, privacy approach and known limitations.
- Link the repository, setup instructions, delivery roadmap and GitHub issues.
- Keep the introduction, examples and recording accessible without an account or running backend. Do not publish an unfinished live client as a working product.

Acceptance: a visitor can understand the project, inspect example behaviour and reach the source on desktop or mobile with the backend completely stopped. Test keyboard navigation, readable labels, links and the walkthrough fallback.

## 2. Build a clearly labelled recorded-example experience

Owner: D with B/C reviewing fixtures and attribution.

- Curate a small set of representative claims, evidence and results; use reviewed fixtures or recorded actual runs, never random verdicts.
- Display a persistent "Recorded example — not a live fact check" label and source/date context where relevant.
- Keep example browsing separate from live check submission. Free-text input must not silently receive an unrelated sample answer.
- Include illustrative unavailable and fallback states, labelled as recorded scenarios.
- Use safe text/URL rendering and strip secrets, personal claims, account details and private logs from published assets.
- Do not imply current verification, calibrated confidence or accuracy established beyond the measured evaluation set.

Acceptance: visitors can identify every sample as prerecorded; no sample action starts paid work, and unavailable live inference never produces a substituted example verdict.

## 3. Make the actual local project reproducible

Owners: A integration, B inference, C evidence, D clients.

- Complete and test the real submission/evidence/inference/result path, preserving exact public statuses and the no-fabrication rule.
- Fix unsafe rendering, capture provenance, crawler destinations and citation validation before advertising the corresponding functionality as usable.
- Document Windows and Unix setup, migrations, web and Q2 worker startup, optional provider credentials and Ollama installation.
- Demonstrate remote success, local fallback and both providers unavailable on the supported local profile.
- Record what was tested, the environment and remaining limitations. Include real hermetic checks and useful browser coverage rather than relying on placeholder scripts.

Acceptance: follow the README from a clean checkout on the supported environment. The recorded walkthrough must match the actual tested behaviour. Broader FAI tasks are not complete until their original acceptance criteria pass.

## 4. Add optional hosted live checks only if worthwhile

Owners: A/D, with B/C reviewing exposed paths.

- Investigate free hosting that can support both the web process and Q2 worker plus appropriate persistent data. A sleeping web service alone is not a complete deployment.
- If the free topology cannot support this reliably, keep live execution local and publish the static showcase. Do not add paid services merely to meet an always-on target.
- Use disposable demonstration data where storage is temporary, document retention and avoid public account creation initially.
- Keep provider keys server-side. Enforce submission limits, queue/concurrency limits and conservative durable spending before enabling paid inference. Provider controls should supplement application limits where available; alerts alone are not a spending cap.
- Display cold-start/unavailable states honestly, with the recorded-example experience still accessible.
- Localhost on a cloud worker is not the developer's Ollama instance. Test secure connectivity if an optional local host is used; otherwise disclose that hosted local fallback is unavailable. Do not advertise full fallback acceptance for that hosted profile.
- Fix every applicable live-path security issue before exposure. Do not publish arbitrary crawling or paid anonymous submissions while those controls are unfinished.

Acceptance: the supported hosted path is tested end to end, budget exhaustion denies paid work, private data is protected, and outage handling never invents results. If this cannot be demonstrated at the agreed budget, omit the live backend.

## 5. Final portfolio review

- [ ] Public showcase works without the backend or account login.
- [ ] Examples are clearly labelled and safely rendered.
- [ ] Walkthrough depicts tested real functionality and has an accessible text explanation.
- [ ] README setup, technical claims and known limitations match the delivered project.
- [ ] Repository and issue links work; no secrets or personal data appear in assets.
- [ ] Optional live features pass their exposed-path security, correctness and budget acceptance.
- [ ] Free-tier limitations and any actual ongoing costs are documented.

## Relationship to the existing backlog

Retain all FAI-01–FAI-48 tasks and original acceptance criteria. Portfolio presentation aligns with FAI-34/36/37/44/45; local reproducibility with FAI-33/45/46; optional hosted work with FAI-27–30/40/48. These are partial alignments, not replacement definitions of done. No task is closed by changing the release profile.

Always-on infrastructure, continuously hosted Ollama, broad public onboarding, high availability and production-scale operations are future scope. The full application's P0 blockers remain mandatory. The full [delivery roadmap](DELIVERY_PLAN.md) and its estimates remain available for that later release; no new portfolio completion date is promised before the showcase and local-path work are inspected.
