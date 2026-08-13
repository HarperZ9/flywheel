# Unified Evidence Journey Rollout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the approved Unified Evidence Journey through five independently useful, evidence-gated releases.

**Architecture:** One deterministic journey record connects existing Flywheel oracles, receipts, bundles, audit/eval routes, and lessons. Frontier research and incidents enter through typed adapters; Domain Packs provide nominal evidence rules without placing a model on the accept path. The desktop renders Rescue, Diagnose, and Verify projections over the same record.

**Tech Stack:** Python 3.11+ standard library verifier path, canonical JSON/SHA-256, existing Flywheel gateway and receipts, Flutter/Dart desktop client, pytest, Flutter test.

## Global Constraints

- No learned model on the accept path.
- No receipt, no accept; denominators and `does_not_prove` are mandatory.
- PASS, FAIL, UNDECIDED, and UNVERIFIABLE remain distinct.
- Evidence kinds are nominal and never collapsed into a universal score.
- Individual developers, engineering leads, and reviewers have equal precedence.
- Rescue, Diagnose, and Verify render the same underlying record.
- New Python and Dart files stay at or below 300 physical lines.
- The verifier path keeps zero third-party runtime dependencies.
- Network retrieval, provider execution, and governance mutation remain outside verification.
- Existing public paths, secrets, private artifacts, and historical receipts never enter fixtures.
- Each implementation task uses RED, GREEN, focused regression, gates, review, then a narrow commit.
- The Can/Stencil reference bar is a reproducible multi-model harness experiment with per-run evidence, resource measures, intervals, denominators, safety controls, and portable rechecks.

---

## Dependency map

```text
Plan 01 Journey spine
  |
  +--> Plan 02 Incident Compiler
  |
  +--> Plan 03 Frontier Claims + Mathematics
             |
             +--> Plan 04 Pack SDK + Physics + Harness Experiments
                              |
                              +--> Plan 05 Interchange + Enterprise Controls
```

## File structure locked by this rollout

| Area | Responsibility |
|---|---|
| `harness/evidence_json.py` | strict JSON, canonical hashes, admitted artifact refs |
| `harness/evidence_journey.py` | journey state machine and three projections |
| `harness/evidence_packet.py` | packet pack/recheck over existing bundle primitives |
| `harness/evidence_route.py` | gateway-neutral journey handlers |
| `harness/incident_*.py` | case schema, source adapters, review gate, lesson bridge |
| `harness/domain_pack.py` | pack manifest validation and registry |
| `harness/frontier_*.py` | source/claim/event records and claim routes |
| `harness/math_pack.py` | Lean-backed math policy and fidelity boundary |
| `harness/physics_*.py` | data-only physics checks and pack |
| `harness/harness_experiment.py` | Can/Stencil-style harness intervention studies |
| `harness/evidence_interchange.py` | evidence-only import/export adapters |
| `desktop/lib/views/journey_view.dart` | default progressive-disclosure journey |
| `desktop/lib/models/evidence_models.dart` | typed client projection of journey records |

## Release sequence

### Release 1: Journey spine

Implement [Plan 01](2026-08-12-unified-evidence-journey-01-spine.md). Exit when a software failure can move through intake, preflight, existing code oracle, conclusion, three lenses, packet export, and offline recheck from both CLI and desktop.

### Release 2: Incident loop

Implement [Plan 02](2026-08-12-unified-evidence-journey-02-incidents.md). Exit when a witnessed audit, eval, provider, or cross-harness failure produces a privacy-reviewed incident, regression fixture, lesson candidate, and independently proven mitigation without automatic policy mutation.

### Release 3: Frontier mathematics

Implement [Plan 03](2026-08-12-unified-evidence-journey-03-frontier-math.md). Exit when versioned research sources produce atomic claims whose formal verdict, novelty, community state, statement fidelity, reproduction, and freshness remain separate and recheckable.

### Release 4: Pack platform and physics

Implement [Plan 04](2026-08-12-unified-evidence-journey-04-packs-physics.md). Exit when a pack author can scaffold, validate, mutation-test, and package a data-only physics pack, and when the harness-experiment pack reproduces the Can/Stencil method with stronger evidence controls.

### Release 5: Interchange and organization controls

Implement [Plan 05](2026-08-12-unified-evidence-journey-05-interchange-enterprise.md). Exit when external traces/evals import only as evidence, exports preserve claim limits, and review, retention, ownership, signatures, contests, and supersession remain recheckable.

## Cross-release acceptance

- [ ] Run `python scripts/check_file_gate.py`; expect 0 new and 0 grown files.
- [ ] Run `python scripts/check_verifier_stdlib.py`; expect closure PASS.
- [ ] Run `python scripts/check_claim_language.py`; expect no public optimality claim.
- [ ] Run `python scripts/check_public_instructions.py`; expect no new path leak.
- [ ] Run `python -m pytest tests/ -q`; expect exit 0.
- [ ] Run `python -m harness.cli_entry gate`; expect PASS and rewitness MATCH.
- [ ] For desktop changes, run `flutter analyze` and `flutter test`; expect exit 0.
- [ ] Export the release acceptance packet and recheck it from a clean temporary directory.
- [ ] Record denominators, platform skips, resource use, and `does_not_prove`; do not infer missing counts.

## Commit policy

Each numbered task in a subplan ends in one scoped commit. Do not combine releases. If implementation changes an approved interface, update the design specification and affected plan first, get review, then modify code.
