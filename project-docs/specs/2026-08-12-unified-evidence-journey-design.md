# Unified Evidence Journey

**Status:** APPROVED DESIGN

**Date:** 2026-08-12

**Decision:** Build one evidence journey with Frontier Claims, Domain Packs, and the Incident Compiler as its first three major capabilities.

**Approved audiences:** individual developers, engineering leads, and independent or enterprise reviewers have equal precedence.

## 1. Purpose

Flywheel should start with a goal, failure, or research claim and end with the next justified action plus a packet another person can independently recheck. It must help an overloaded developer make progress, help a senior engineer diagnose and improve a system, and help a reviewer establish what the evidence does and does not support. These are views over one record, not three products.

The design extends Flywheel's verified core instead of becoming another trace viewer. Traces are evidence inputs. They are not the product boundary and never decide a verdict.

## 2. Problem

The engine already has typed verdicts, fail-closed oracles, receipts, provenance, honest nulls, admission controls, offline rechecks, lessons, and deterministic reports. Its weakness is conversion:

1. Capability is spread across Run, Plan, Audit, Eval, Compare, Workflow, Endpoint, and evidence surfaces.
2. The default registry covers code, formal mathematics, and measured ML, but not coherent domain packs for most fields.
3. Fast research arrives as papers and headlines without a durable path from source capture to atomic claims, independent checks, revisions, and expiry.
4. Incidents and model failures do not automatically become governed regression cases and reusable lessons.
5. A formal checker can prove that a term inhabits a stated theorem without proving that the theorem represents the intended claim.

## 3. Product principles

1. **One record, progressive disclosure.** Answer first, explanation second, complete evidence third.
2. **No model on the accept path.** Models may propose, decompose, translate, or explain. Registered checkers and human attestations decide.
3. **No receipt, no accept.** Every conclusion binds inputs, criteria, checker identities, denominators, limitations, and raw-evidence references.
4. **Claim state is not one score.** Machine verdict, evidence kind, community review, novelty, freshness, and statement fidelity remain orthogonal.
5. **No universal evidence ladder.** Formal proof, numerical reproduction, simulation, empirical observation, and expert attestation are nominal kinds. A pack defines the admissible combination for a claim type.
6. **Unknown beats plausible.** Missing tools, absent evidence, unsupported domains, and stale attestations produce typed UNVERIFIABLE results.
7. **Strict truth, gentle recovery.** Failed work becomes a useful case, not a corrupted run or permanent sentence.
8. **Local-first verification.** The load-bearing packet and recheck path work without an account or provider connection whenever the domain permits it.
9. **Human judgment is evidence.** Attestations name the expert, scope, basis, expiry, conflicts, and omissions. They are not hidden labels.
10. **Every incident improves the environment.** A witnessed failure should leave a minimized case, invariant, regression, and reviewable lesson.

## 4. User contract

The journey has six stages:

1. **Intake:** accept a goal, failed run, artifact, paper, dataset, or claim.
2. **Decompose:** produce atomic, falsifiable claims and identify dependencies.
3. **Preflight:** show the domain pack, required evidence, available checkers, cost, permissions, missing witnesses, and stop conditions.
4. **Run:** collect evidence through isolated, bounded tools and named humans.
5. **Conclude:** issue typed verdicts, honest nulls, limitations, and next actions.
6. **Export:** seal a trust packet and optionally derive incidents, lessons, evaluation cases, or governance proposals.

Each stage renders through three equally supported lenses:

- **Rescue:** the smallest safe next action, expected effect, and rollback.
- **Diagnose:** causal evidence, alternatives tested, disagreements, and reruns.
- **Verify:** criteria, artifacts, hashes, attestations, recheck commands, and contest history.

Changing lenses never changes the evidence or conclusion.

## 5. Architecture

```text
goal / incident / paper / claim
              |
        Evidence Journey
              |
     atomic claim dependency graph
              |
        Domain Pack registry
              |
  proposals -> checkers -> attestations
              |
     orthogonal claim-state projection
              |
 action / repair | trust packet | incident | lesson
```

Four versioned envelopes define the boundary:

- `flywheel.evidence-journey/v1`
- `flywheel.frontier-claim/v1`
- `flywheel.domain-pack/v1`
- `flywheel.incident-case/v1`

All use canonical JSON for hashed bodies, reject duplicate keys and non-finite numbers, bind relative artifact references, and keep self-referential receipt fields outside their own digest.

## 6. Unified Evidence Journey

The journey orchestrator is a deterministic state machine over referenced artifacts. It contains no domain logic. It resolves a pack, checks admission, dispatches registered verifiers, records attestations, and projects the result for each user lens.

The journey record contains:

- goal, scope, and atomic claim graph;
- source, prompt, input, environment, policy, and toolchain hashes;
- domain-pack id, version, and manifest hash;
- planned and observed checks, including omissions;
- raw evidence refs and sanitized presentation refs;
- machine verdicts, reason codes, and statement-fidelity attestations;
- denominators, resource use, and timeout state;
- derived next actions and their evidence basis;
- receipt, contest, invalidation, and supersession refs.

Derived guidance cites the evidence fields it uses. Guidance is advisory and cannot mutate the verdict.

## 7. Frontier Claims

Frontier Claims handles rapidly changing research without turning announcements into accepted discoveries.

### 7.1 Intake and decomposition

The intake plane captures immutable source versions: publication time, authorship, identifier, source hash, retrieval facts, and revisions. Network retrieval stays outside the accept path. A claim can come from a URL, DOI, arXiv version, local paper, dataset, or trust packet.

Sources are decomposed into atomic theorem, counterexample, equivalence, reduction, numerical, empirical, causal, novelty, performance, and limitation claims. Model-produced decomposition remains proposed until admitted by the pack schema and, when required, a human reviewer.

### 7.2 Orthogonal state

A frontier claim carries independent axes:

- `review_state`: captured, decomposed, admitted, checking, or closed;
- `verdict`: PASS, FAIL, UNDECIDED, or UNVERIFIABLE;
- `evidence_kind`: one or more pack-defined nominal kinds;
- `community_state`: unreviewed, under_review, contested, accepted, or superseded;
- `novelty_state`: REDISCOVERY, NOT_FOUND_IN_CORPUS, or UNKNOWN;
- `fidelity_state`: unattested, attested, contested, expired, or not_applicable;
- `freshness_state`: current, recheck_due, stale, or immutable;
- `reproduction_state`: not_attempted, partial, matched, drifted, or blocked.

No renderer may collapse these axes into a trust score or replace them with a headline such as "solved."

### 7.3 Revision and watch behavior

New versions append events and never rewrite the original claim. A scheduler may propose rechecks when a source changes, attestation expires, checker is revoked, contest arrives, or dependency is superseded. Retrieval and recheck remain budgeted and operator-controlled.

## 8. Domain Pack SDK

A pack is a declarative manifest plus checkers, fixtures, and rendering rules. Its manifest specifies:

- domain and claim-type identifiers, applicability, and refusal rules;
- required evidence combinations and checker identities;
- checker source hashes, isolation, determinism, and second-checker requirements;
- human-attestation roles and expiry;
- mutation, negative-control, and calibration fixtures;
- typed failure and UNVERIFIABLE reasons;
- mandatory `does_not_prove` statements;
- invalidation, compatibility, presentation, and redaction policy.

Registration is deny-by-default. A pack without passing fixtures, checker QA, and limitations may assist exploration but cannot issue an admissible PASS.

### 8.1 Mathematics pack

Extend the Lean path with theorem-statement hashes, axiom and admitted-hole audits, toolchain pins, independent checking for consequential claims, source-to-formal-statement links, novelty search, and separate statement-fidelity attestation. A kernel PASS never proves novelty, importance, authorship, or fidelity to the intended theorem.

### 8.2 Physics pack

Support symbolic derivation, dimensional analysis, numerical reproduction, simulation provenance, sensitivity analysis, uncertainty, known-limit checks, dataset lineage, and empirical replication. Each claim type selects an admissible combination. A formal derivation cannot by itself establish that a physical model describes nature.

### 8.3 Authoring experience

The SDK supplies a scaffold command, schema validator, fixture runner, mutation runner, independent-checker test, example trust packet, and pack doctor. The fastest useful pack is small and explicit. The registry should refuse unmaintained integrations without an oracle or owner.

## 9. Incident Compiler

The compiler converts witnessed failures into proposed governance and evaluation assets. Inputs include failed receipts, blocked attempts, policy violations, provider rejections, drift, contests, and operator-authored cases.

Its output contains:

- sanitized minimal reproduction and immutable source refs;
- failure class, affected boundary, preconditions, and blast radius;
- observed versus expected behavior;
- proposed invariant, owner, regression fixture, and test matrix;
- mitigation link and before/after evidence;
- recurrence, expiry, and retirement criteria;
- lesson candidate and governance-change proposal.

The compiler may draft tests and policy changes but cannot admit them. Human review confirms minimization, privacy, expected behavior, and preservation safety. A mitigation is complete only after the original case and relevant controls are rerun and independently rechecked.

## 10. Existing components to reuse

| Need | Existing primitive |
|---|---|
| Four-way verdict and refusal | oracle registry and oracle protocol |
| Formal proof checking | Lean oracle |
| Measured ML claims | measurement oracle |
| Evidence sealing and replay | receipts, ledger, bundle, world, recheck paths |
| Cross-harness failure facts | typed executor and comparison artifacts |
| Generated-artifact review | audit and eval routes |
| Organizational memory | lesson, lesson store, patterns, mappers |
| Verified training signal | RL-from-oracle signal generation |
| Multi-tool intake and routing | lanes, gather, forum, index, gateway |
| Native presentation | desktop and gateway, with no verdict reimplementation |

Connect these primitives first. Add a component only where no existing boundary can carry the contract.

## 11. Security, governance, and interchange

- Verifiers run with deny-by-default execution, network, write, and secret access.
- Raw sources and traces are content-addressed and private by default.
- Export performs redaction and secret scanning before packing.
- Provider- or model-authored identity is never treated as attested identity.
- Human attestations are signed outside model reach where signing is enabled.
- Packs declare data residency and retention requirements.
- Imports cannot execute embedded code or escape their admitted root.
- Contests, corrections, supersessions, and governance changes append to history.

OpenTelemetry, MLflow, Phoenix, Langfuse, and other formats may be imported as evidence and exported as views. Their stored scores do not become Flywheel verdicts. The native packet remains authoritative because it carries criteria, checker pins, raw refs, limitations, and recheck commands.

## 12. Testing and acceptance

Every capability requires schema and duplicate-key rejection; malformed, missing, timeout, drift, and unavailable cases; path containment; planted false-accept and false-reject mutations; packet recheck; exact denominators; fidelity disagreement and expiry; secret-redaction tests; identical results across all three lenses; and an incident that becomes a regression and later proves its mitigation.

No pack is generally available until its corpus includes a correct, incorrect, ambiguous, malformed, stale, contested, and unsupported claim.

## 13. Delivery sequence

1. **Journey spine:** envelopes, state machine, three projections, existing-oracle dispatch, trust packet, and one software-failure flow.
2. **Incident Compiler:** connect audit, eval, cross-harness, and provider failures to cases, regression fixtures, and lessons. Prove it on the known July/August corpus.
3. **Frontier Claims and mathematics pack:** versioned intake, claim graphs, revision tracking, fidelity attestations, and a corpus of accepted, contested, partial, rediscovered, and unsupported examples.
4. **Physics pack and Pack SDK:** symbolic, numerical, simulation, uncertainty, and empirical workflows. Validate the SDK with a third domain outside the core team.
5. **Interchange and enterprise controls:** adapters, review queues, ownership, retention, signed attestations, contests, and organization views.

## 14. Success measures

Measures stay separate by audience and never form a composite trust score:

- Rescue: time to first justified action, successful rerun rate, rollback rate.
- Diagnose: reproduced-failure rate, causal-alternative coverage, regression yield.
- Verify: packet recheck success, missing-evidence rate, contest resolution time.
- Frontier: time to decomposed claims, verification backlog, revision detection, fidelity coverage, rediscovery rate.
- Domain packs: QA false accepts, unsupported-claim refusal, checker agreement, ownership, recheck cost.
- Incident loop: incidents converted, mitigations independently proven, recurrence, stale or retired cases.

## 15. Explicit non-goals

- A general truth, researcher, model, or organization score.
- Consensus voting as verification.
- Treating formal proof as proof of statement intent or physical reality.
- Automatically declaring novelty, importance, or scientific acceptance.
- Autonomous policy deployment or incident suppression.
- Replacing specialist tools, laboratories, peer review, or domain experts.
- Another trace dashboard whose stored judgment cannot be re-derived.

## 16. Implementation-plan decisions

1. Whether the journey log extends the existing ledger or projects over it.
2. The minimum attestation identity and signature scheme.
3. The desktop entry point and advanced surfaces that become projections.
4. The initial physics corpus and safe simulation boundary.
5. Retention for copyrighted papers and sensitive datasets.
6. Compatibility rules for independently distributed packs.

These decisions do not change the approved architecture. The implementation plan must settle them through explicit tradeoffs and tests.
