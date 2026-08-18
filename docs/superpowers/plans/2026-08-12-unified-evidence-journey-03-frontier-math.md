# Unified Evidence Journey 03 Frontier Mathematics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn fast-moving research sources into versioned atomic claims whose machine verdict, evidence kind, review, novelty, fidelity, freshness, and reproduction state remain independent.

**Architecture:** Source capture stores hashes and retrieval facts outside the accept path. A deterministic claim log appends revisions and contests. The mathematics pack wraps the existing Lean oracle but adds theorem-statement, axiom, hole, toolchain, novelty, and statement-fidelity boundaries.

**Tech Stack:** Python standard library, journey spine, oracle registry, Lean oracle, bundle/receipt primitives, pytest.

## Fixed boundaries

- Raw copyrighted papers are private references by default; exports carry metadata, hashes, excerpts only when licensed, and operator-approved refs.
- Network retrieval never decides a verdict and is excluded from offline recheck.
- Community acceptance and novelty are evidence axes, not proof verdicts.
- Kernel PASS cannot establish intended meaning, authorship, importance, physical truth, or novelty.

---

### Task 1: Frontier source and claim envelopes

**Files:**
- Create: `harness/frontier_claim.py`
- Create: `harness/frontier_store.py`
- Create: `tests/test_frontier_claim.py`
- Create: `tests/test_frontier_store.py`

- [ ] Write RED tests for `flywheel.frontier-claim/v1`, immutable source versions, atomic claim graph, source and retrieval hashes, append-only revisions, contests, invalidations, and the exact independent axes `review_state`, `verdict`, `evidence_kind`, `community_state`, `novelty_state`, `fidelity_state`, `freshness_state`, and `reproduction_state`.
- [ ] Cover duplicate keys, non-finite values, cycles, invalid enum values, unknown source version, stale/expired attestations, attempted overwrite, and renderer collapse into one score.
- [ ] Implement:

```python
def new_frontier_claim(*, claim_id: str, source: dict,
                       proposition: dict, created_at: str) -> dict: ...
def append_claim_event(claim: dict, event: dict) -> dict: ...
def project_claim(claim: dict) -> dict: ...
class FrontierStore:
    def append(self, claim: dict) -> str: ...
    def load(self, claim_id: str) -> dict: ...
```

Store content-addressed versions and an append-only head record. Never rewrite a prior source or claim event.
- [ ] Run focused tests; expect PASS.
- [ ] Commit: `feat: add frontier claim ledger`.

### Task 2: Deterministic intake and decomposition admission

**Files:**
- Create: `harness/frontier_intake.py`
- Create: `tests/test_frontier_intake.py`

- [ ] Write RED tests for local file, URL metadata, DOI/arXiv identifiers, dataset manifest, and trust-packet intake. Retrieval input is already-fetched bytes plus facts; tests must prove no network call occurs.
- [ ] Add decomposition tests for theorem, counterexample, equivalence, reduction, numerical, empirical, causal, novelty, performance, and limitation claim types. Model-produced decompositions start `proposed` and cannot reach `admitted` without schema and required human review.
- [ ] Implement:

```python
def capture_source(content: bytes | None, facts: dict) -> dict: ...
def propose_claims(source: dict, proposals: list[dict]) -> list[dict]: ...
def admit_claim(claim: dict, *, pack: dict, attestation: dict | None) -> dict: ...
```

- [ ] Run focused tests; expect PASS.
- [ ] Commit: `feat: admit versioned frontier claims`.

### Task 3: Domain pack manifest and deny-by-default registry

**Files:**
- Create: `harness/domain_pack.py`
- Create: `tests/test_domain_pack.py`
- Modify: `harness/oracle_registry.py`
- Modify: `tests/test_oracle_registry.py`

- [ ] Write RED tests for `flywheel.domain-pack/v1`: domain/claim ids, applicability/refusal, required nominal evidence combinations, checker id/version/source hash, isolation/determinism, second-checker rule, attestation roles/expiry, fixtures, failure reasons, limitations, redaction, owner, retirement, and compatible schema versions.
- [ ] Assert unregistered, unowned, fixture-failing, missing-source-hash, or unsupported-version packs can assist exploration but cannot issue admissible PASS.
- [ ] Implement `DomainPackRegistry.register_verified(manifest, qa_receipt)` and `resolve(domain, claim_type)`. Keep the existing oracle registry API stable; pack resolution returns registered oracle ids rather than executing arbitrary plugins.
- [ ] Run domain/oracle suites; expect PASS.
- [ ] Commit: `feat: register verified domain packs`.

### Task 4: Mathematics pack and fidelity boundary

**Files:**
- Create: `harness/math_pack.py`
- Create: `tests/test_math_pack.py`
- Create: `benchmarks/fixtures/domain-packs/math-pack-v1.json`

- [ ] Write RED tests for theorem statement hash, Lean source hash, toolchain pin, axiom inventory, `sorry`/admitted-hole refusal, independent-checker requirement, novelty search facts, and statement-fidelity attestation.
- [ ] Include cases: valid theorem with attested fidelity; kernel PASS but unattested intent; wrong theorem proving an easier statement; admitted hole; checker unavailable; rediscovery; novelty corpus miss reported as `NOT_FOUND_IN_CORPUS`; contested fidelity; expired attestation.
- [ ] Implement a pack policy that calls the existing Lean oracle and then projects separate proof, novelty, and fidelity axes. Never translate `NOT_FOUND_IN_CORPUS` to novel.
- [ ] Run `python -m pytest tests/test_math_pack.py tests/test_lean_oracle.py tests/test_oracle_registry.py -q`; expect PASS.
- [ ] Commit: `feat: add fidelity-aware mathematics pack`.

### Task 5: Frontier routes, watch proposals, and desktop

**Files:**
- Create: `harness/frontier_route.py`
- Create: `harness/frontier_cli.py`
- Create: `tests/test_frontier_route.py`
- Create: `tests/test_frontier_cli.py`
- Create: `desktop/lib/views/frontier_view.dart`
- Create: `desktop/test/frontier_view_test.dart`
- Modify: `harness/gateway.py`
- Modify: `harness/cli_entry.py`
- Modify: `desktop/lib/main.dart`

- [ ] Write RED tests for capture, decompose, admit, check, contest, supersede, project, and recheck. A watch operation may propose a recheck after source revision, expiry, checker revocation, contest, or dependency supersession but cannot retrieve or execute it automatically.
- [ ] Write widget tests showing proposition and current verdict first, orthogonal axes second, source/event/recheck details third, with explicit `unreviewed`, `contested`, and `unverifiable` states.
- [ ] Implement thin route/CLI dispatch and the Frontier desktop destination. Offset frozen-file line growth.
- [ ] Run focused Python and Flutter tests; expect PASS.
- [ ] Commit: `feat: expose frontier claim review`.

### Task 6: Calibrated mathematics corpus and packet

**Files:**
- Create: `benchmarks/fixtures/frontier-math/corpus-v1.json`
- Create: `tests/test_frontier_math_corpus.py`
- Create: `project-docs/records/2026-08-12-frontier-math-pack.md`

- [ ] Add public-safe, attribution-backed fixtures covering correct, incorrect, ambiguous, malformed, stale, contested, rediscovered, and unsupported claims. Include a Riemann Hypothesis progress claim classified without saying the hypothesis is solved unless a registered proof and fidelity review support that exact proposition.
- [ ] Run mutations that swap theorem statements, citations, source versions, checker hashes, novelty corpora, and attestations. Record false accepts/refusals, denominators, checker agreement, recheck cost, and limitations.
- [ ] Export and recheck the corpus packet offline. Run full Python/static gates and secret/path scans.
- [ ] Request spec and quality review, remediate, rerun, and commit: `test: calibrate frontier mathematics evidence`.
