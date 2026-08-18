# Unified Evidence Journey 04 Packs Physics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make verified domain packs authorable and ship a data-only physics pack plus a harness-experiment pack that matches the Can/Stencil empirical method and adds Flywheel evidence controls.

**Architecture:** The SDK scaffolds manifests, fixtures, and checker adapters but registers only QA-passing packs. Physics checkers consume admitted data and manifests, never uploaded candidate code. The harness-experiment pack freezes intervention, task generator, environment, repetitions, and measures before execution.

**Tech Stack:** Python standard library verifier path, existing oracle/domain-pack registry, optional external tools behind typed adapters, pytest.

## Fixed boundaries

- Simulation intake accepts results and provenance manifests only; it never executes uploaded simulation code.
- Pack compatibility requires exact schema version, checker id/version/source hash, and an explicit compatibility declaration.
- Distributed packs are denied until owner, QA receipt, limitations, and retirement policy verify.
- External benchmark numbers are source claims, not built-in targets. Flywheel compares method coverage and its own frozen results.

---

### Task 1: Pack scaffold and manifest CLI

**Files:**
- Create: `harness/domain_pack_cli.py`
- Create: `harness/pack_scaffold.py`
- Create: `tests/test_domain_pack_cli.py`
- Create: `tests/test_pack_scaffold.py`
- Modify: `harness/cli_entry.py`

- [ ] Write RED tests for `pack new`, `validate`, `fixtures`, `mutate`, `doctor`, and `example-packet`; ASCII help; packaged-wheel operation; safe ids; empty-directory creation; no overwrite; no host paths; and deterministic scaffold bytes.
- [ ] Implement a scaffold containing a manifest, checker adapter, correct/incorrect/ambiguous/malformed/stale/contested/unsupported fixtures, test skeleton, limitations, and owner/retirement metadata.
- [ ] Keep CLI dispatch compact and offset every line in the frozen entrypoint.
- [ ] Run focused CLI/scaffold and wheel-smoke tests; expect PASS.
- [ ] Commit: `feat: scaffold verified domain packs`.

### Task 2: Pack QA and mutation gate

**Files:**
- Create: `harness/pack_qa.py`
- Create: `tests/test_pack_qa.py`

- [ ] Write RED tests for fixture completeness, schema mutations, evidence removal, checker-id/hash drift, verdict widening, false-accept/false-reject plants, nondeterminism, missing limitations, expired owner, absent second checker, and unsupported claim refusal.
- [ ] Implement:

```python
def run_pack_qa(pack_dir: Path, *, registry: OracleRegistry) -> dict: ...
def mutate_pack_fixtures(pack_dir: Path, *, seed: int) -> dict: ...
def issue_pack_qa_receipt(report: dict, *, out_dir: Path) -> dict: ...
```

The QA receipt records mutation denominator, detected/escaped mutations, platform skips, runtime, checker facts, and `does_not_prove`. Escaped false accepts block registration.
- [ ] Run pack/domain/oracle suites; expect PASS.
- [ ] Commit: `feat: gate packs with mutation evidence`.

### Task 3: Physics data boundaries

**Files:**
- Create: `harness/physics_units.py`
- Create: `harness/physics_oracle.py`
- Create: `tests/test_physics_units.py`
- Create: `tests/test_physics_oracle.py`

- [ ] Write RED tests for canonical dimensions and units, exact/ranged quantities, uncertainty intervals, significant metadata, non-finite numbers, inconsistent dimensions, interval reversal, missing uncertainty, and safe relative data refs.
- [ ] Add data-only checkers for symbolic-derivation manifest, dimensional consistency, numerical reproduction interval, simulation provenance, sensitivity samples, known-limit samples, dataset lineage, and empirical replication refs.
- [ ] Implement:

```python
def check_dimensions(claim: dict, evidence: dict) -> OracleResult: ...
def check_numerical_interval(claim: dict, evidence: dict) -> OracleResult: ...
def check_simulation_provenance(manifest: dict, *, root: Path) -> OracleResult: ...
def check_known_limits(claim: dict, samples: list[dict]) -> OracleResult: ...
```

Reject command fields, executable refs, embedded code, network URLs used as local evidence, and any attempt to run a candidate. Formal or numerical PASS includes a physical-truth limitation.
- [ ] Run focused tests; expect PASS.
- [ ] Commit: `feat: add data-only physics checks`.

### Task 4: Physics pack policy and corpus

**Files:**
- Create: `harness/physics_pack.py`
- Create: `benchmarks/fixtures/domain-packs/physics-pack-v1.json`
- Create: `benchmarks/fixtures/frontier-physics/corpus-v1.json`
- Create: `tests/test_physics_pack.py`

- [ ] Write RED tests mapping claim types to admissible nominal evidence combinations: derivation, dimensional, numerical, simulation, uncertainty, known-limit, lineage, empirical, and expert attestation.
- [ ] Include correct, incorrect, ambiguous, malformed, stale, contested, unsupported, unit-mismatch, overfit-limit, untracked-simulation, and empirical-disagreement fixtures.
- [ ] Implement pack registration and refusal. Require independent evidence for consequential empirical claims; a derivation alone never closes an empirical claim.
- [ ] Run physics pack QA and mutation gate; expect no escaped planted false accept.
- [ ] Commit: `feat: register calibrated physics pack`.

### Task 5: Can/Stencil-style harness experiment pack

**Files:**
- Create: `harness/harness_experiment.py`
- Create: `benchmarks/fixtures/domain-packs/harness-experiment-pack-v1.json`
- Create: `tests/test_harness_experiment.py`

- [ ] Write RED tests for preregistered hypothesis, isolated intervention, frozen generator/source hash, heterogeneous model roles, at least three repetitions, exact task matrix, seed/cache/context/tool policy, exclusions, abort rules, per-run refs, success/tokens/latency/cost, intervals, denominators, failures, abstentions, integrity/safety controls, user-outcome proxy, and transfer limits.
- [ ] Implement:

```python
def admit_experiment(plan: dict) -> dict: ...
def expand_experiment(plan: dict) -> list[dict]: ...
def summarize_experiment(plan: dict, runs: list[dict]) -> dict: ...
def recheck_experiment(packet_dir: Path) -> dict: ...
```

Reject post-hoc hypothesis changes, intervention drift, missing runs, silent retry, selective exclusions, denominator mismatch, model self-attestation, and unregistered outcome measures. Preserve null costs and resources with reasons.
- [ ] Add frozen method fixtures for context, edit, tool, error, and state-management intervention families. Do not encode a winner or Stencil's reported point estimates.
- [ ] Run focused tests and pack QA; expect PASS.
- [ ] Commit: `feat: add reproducible harness experiment pack`.

### Task 6: Third-party authoring proof and release record

**Files:**
- Create: `examples/domain-packs/tabular-data-quality/`
- Create: `tests/test_domain_pack_example.py`
- Create: `project-docs/records/2026-08-12-domain-pack-sdk.md`

- [ ] Use the public scaffold as a fresh author would to create a small tabular-data-quality pack. Do not import private helpers. Cover schema conformity, missingness, range, uniqueness, and unsupported semantic claims.
- [ ] Run scaffold, validator, fixtures, mutation runner, doctor, example packet, physics pack, harness-experiment pack, and clean-directory rechecks.
- [ ] Record time-to-first-pack, commands, mutation denominators, false accepts/refusals, recheck cost, limitations, maintenance owner, and retirement criteria.
- [ ] Run full Python/static/package/secret/path gates. Request spec and quality review, remediate, rerun, and commit: `test: verify domain pack authoring path`.
