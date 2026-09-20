# Native decision contract implementation plan

**Goal:** Build a native harness contract for constrained choice proposals and a falsifiable offline evaluation surface.

**Architecture:** Pure bounded proposal validation uses existing canonical hashing. Evaluation measures semantic labels separately from contract validity; execution and authorization remain existing independent boundaries.

**Tech stack:** Python stdlib and existing pytest infrastructure.

**Spec:** `docs/superpowers/specs/2026-09-16-native-decision-contract.md`.

## Constraints

No runtime dependencies, no provider calls, no new authoritative store, no learned acceptance. Files stay below300lines. Source-only contract/control fixtures do not prove model performance. Preserve parallel-owned work.

## Task1: Decision contract

Owner: assigned contract worker. Create `harness/decision_contract.py`, optionally split validation into `harness/decision_validation.py`, and `tests/test_decision_contract.py`. Reuse `harness.evidence_json.canonical_sha256` where its semantics match the contract.

- [ ] Write failing tests for request validation, selected/abstain and response negative controls.
- [ ] Implement `validate_request(payload: dict) -> dict` returning an independent validated JSON snapshot.
- [ ] Implement `evaluate_proposal(request: dict, response: str, *, scorer_ref: str) -> dict` returning the versioned result.
- [ ] Test mutation isolation, duplicate keys/IDs, nonfinite values, oversized input, invented references, unavailable/unknown choice and empty eligibility.
- [ ] Run focused tests, file/stdlib/public-claim gates. Freeze for independent review, no commit until combined checks.

## Task2: Offline evaluation

Owner: root after Task1 interface freeze. Create `harness/decision_evaluation.py`, focused tests and an example runner/fixture with explicit synthetic-control labeling. Consume evaluate_proposal results and independent allowed-answer labels; do not derive truth from selected ids or scorer confidence.

- [ ] Build wrong-but-valid, abstain-all, ineligible and correct controls.
- [ ] Report denominators, selection coverage, selective accuracy, overall correct fraction and invalid selections; unknowns remain null.
- [ ] Run controls and retain machine-readable output plus methodology.
- [ ] Review before any live gateway integration or performance claim.

## Task3: Evidence and integration decision

- [ ] Combine current primary literature with actual local baseline results.
- [ ] Select smallest credible next scorer experiment and fixed held-out tasks before training.
- [ ] Keep gateway/native UI mounting, local model measurement and multimodal support explicitly open until implemented and checked.
