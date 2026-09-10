# Bulletin evaluation bridge implementation plan

**Goal:** Make one independently checked agent handoff usable by an evaluator.
**Architecture:** Optional contract/observer/report adapter, existing Bulletin
HTTP and Journey v2 structures, no new orchestrator or storage protocol.
**Tech stack:** Python stdlib; optional Node/Miniflare for local Worker E2E.
**Spec:** `../specs/2026-09-09-bulletin-evaluation-bridge-design.md`.

- [ ] Write false-success tests before implementing contract and pure oracle.
- [ ] Add bounded HTTP observer and validate pagination/loss/redirect controls.
- [ ] Project checks into Journey v2 and emit via existing artifact writer.
- [ ] Exercise real local Worker signing, semantic controls and response loss.
- [ ] Exercise isolated FeedRoom replay overflow and restart behavior.
- [ ] Run focused tests, relevant gates and review public/private boundaries.
- [ ] Commit and push a draft PR; retain missing controls as explicit limitations.

Owned files are new `harness/bulletin_task_contract.py`,
`harness/bulletin_observer.py`, `harness/bulletin_task_review.py`, associated
tests, driver and docs. Existing Service Desk report and environment v1 files
belong to another owner and are not changed.
