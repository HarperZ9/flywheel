# Spec: Enterprise environment service desk incident slice

## Objective

Build the first private synthetic enterprise-environment product slice from the accepted V2 contract. The slice provides a reusable stdlib framework core plus an independently versioned `service-desk-incident/v1` environment package. It proves real agent API requests can mutate local app state and that the oracle grades server-derived action/state receipts, not model prose or submitted logs.

## Requirements

- [ ] Create `harness.enterprise_envs` with descriptor validation, domain-separated digests, artifact-root preflight, state snapshots, action events, token redaction, and review artifacts.
- [ ] Create `harness.enterprise_envs.envs.service_desk_incident_v1` with descriptor, source-basis metadata, deterministic seed, policy, ServiceDesk API, transitions, oracle, calibration cases, E2E cases, and review HTML.
- [ ] Use real stdlib HTTP requests in focused E2E. The agent surface must not expose hidden control state, reset, oracle, fixture files, or control tokens.
- [ ] Persist only token digests/refs in artifacts. Runtime bearer values remain in memory and are invalidated before finalization.
- [ ] Derive action logs from the server's accepted/denied requests and database mutations. Never accept model-submitted logs as evidence.
- [ ] Implement noncircular digest domains for domain state, action events, action logs, snapshots, reset receipts, isolation receipts, oracle results, and run receipts.
- [ ] Implement reset atomicity, restart/crash recovery checks, concurrent isolation, double-action idempotency, and zero-false-accept calibration.
- [ ] Keep provider/model/vendor calls, cross-harness registration, CLI registry wiring, release actions, and full-suite execution out of scope.
- [ ] Package the environment as an independent product distribution with import namespace `service_desk_incident_env`, CLI `service-desk-incident-env`, and engine prerequisite `flywheel-verify>=0.6.1,<0.7`.
- [ ] Keep `harness.enterprise_envs` importable without the product installed; optional compatibility dispatch must fail with a typed product-missing error.

## Technical Approach

Use `sqlite3`, `http.server`, `threading`, `secrets`, `hashlib`, `json`, and `urllib` only. Start per-run agent and control servers on separate loopback ports. The model-visible runtime view exists only in memory. Persisted receipts use digests and redacted views.

The product CLI lives at `service-desk-incident-env` / `python -m service_desk_incident_env.cli`. The prior `python -m harness.enterprise_envs.cli` path is compatibility-only and lazy-loads the separate product when present, so no shared `harness/cli_entry.py` registry edit is needed before root coordination.

## Files to Modify

- `harness/enterprise_envs/*` - reusable framework core.
- `packages/service-desk-incident-env/src/service_desk_incident_env/v1/*` - independently versioned first environment product implementation.
- `harness/enterprise_envs/envs/service_desk_incident_v1/*` - compatibility shims only, no mirrored implementation.
- `tests/enterprise_envs/*` - focused unit, property-style, and HTTP E2E tests.
- `project-docs/specs/SPEC-2026-09-08-enterprise-env-service-desk.md` - this reviewed implementation spec.

## Success Criteria

- [ ] Focused tests fail before implementation for missing behavior, then pass after implementation.
- [ ] `python -m pytest tests/enterprise_envs -q` passes.
- [ ] `python -m service_desk_incident_env.cli e2e --out <scratch>` produces request/action/resulting-state artifacts and hidden-control-denial evidence.
- [ ] No live bearer token appears in persisted artifacts.
- [ ] No shared cross-harness or CLI registry file is edited.

## Blockers

None for the isolated private synthetic implementation. Cross-harness registration and `flywheel env` registry wiring remain blocked on root coordination.

## Status: APPROVED_FOR_PRIVATE_SYNTHETIC_IMPLEMENTATION

Approval basis: `ENTERPRISE-ENVIRONMENT-FIRST-PRODUCT-CONTRACT-V2-INDEPENDENT-REREVIEW-PASS-20260908.md` with SHA-256 `c24a6851e86171a91c27b9ad730475bd17339aab2732ea9bd3727804598019e9`.


## Packaging prerequisite update - 2026-09-08

Root accepted the separate distribution/import/CLI direction with the correction that `flywheel-verify 0.6.0` is not a valid production minimum because it does not contain `harness.enterprise_envs`. The independent package must require the first engine release containing this API, planned as `flywheel-verify>=0.6.1,<0.7`. Source/package slice tests may use the current checkout engine, but dependency-resolution E2E is deferred until root assembles the engine candidate.
