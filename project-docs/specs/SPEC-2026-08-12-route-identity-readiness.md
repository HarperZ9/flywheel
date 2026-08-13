# Spec: Route identity and local endpoint readiness

## Objective

Make model and endpoint identity exact before any new live benchmark attempt.
Correct the Spark executable selector, stop treating requests as observations,
and bind each local role to one trained release profile and digest.

## Canonical design

`docs/superpowers/specs/2026-08-12-route-identity-readiness-design.md`

## Requirements

- [ ] Advance the cross-harness adapter contract to an explicit identity
      schema without coercing the historical v1 contract.
- [ ] Bind Spark to canonical `gpt-5.3-codex-spark` and display
      `GPT-5.3-Codex-Spark`.
- [ ] Pass only the requested provider reference to the CLI.
- [ ] Keep observed identity empty unless structured provider evidence attests
      it, and name the observation basis.
- [ ] Bind local roles to the exact trained release Ollama profiles.
- [ ] Require exact profile id, backend, model reference and profile hash.
- [ ] Require expected/observed Ollama digest equality.
- [ ] Strip the receipt namespace before native Ollama API calls and verify the
      returned response model.
- [ ] Keep Attempt 6 immutable.
- [ ] Make zero provider calls, zero endpoint calls and zero service changes in
      this implementation slice.

## Technical approach

1. Add contract, manifest, executor, adapter and gate tests and verify RED.
2. Introduce the v2 identity fields and migrate checked-in consumers.
3. Implement exact local selection and digest comparison.
4. Correct native Ollama request/response identity handling.
5. Run focused suites, file/static gates, then the full repository suite.
6. Request independent spec and quality review.

## Expected files

- `benchmarks/cross-harness-adapter-contract-v2.json`
- checked-in callers that currently reference the v1 contract
- `harness/cross_harness_manifest.py`
- `harness/cross_harness_executor.py`
- `harness/cross_harness_adapters.py`
- `harness/adapter_runtime_matrix.py`
- `harness/model_profiles.py`
- `harness/ollama-manifest-digest-provenance-v1.json`
- `harness/local_agent.py`
- `pyproject.toml` (package the provenance artifact)
- endpoint profile/gate producers if expected digest fields must be emitted
- focused tests for every modified surface, including a bounded round-2
  review regression file where existing frozen test files cannot grow

The implementation must update this list before adding any unexpected file.

## Success criteria

- [ ] RED failures demonstrate the overloaded Spark model field, fabricated
      observation, ambiguous local selection, digest-presence gate and native
      Ollama selector defect.
- [ ] GREEN tests prove each corrected behavior.
- [ ] No process/provider/network seam is invoked by the new tests.
- [ ] All frozen files meet their line ceilings.
- [ ] Full tests and public repository gates pass.
- [ ] Independent reviews pass.

## Operational blockers retained

- Exact Spark compatibility with the pinned CLI remains unknown until one
  separately approved route-readiness call.
- Ollama tags and release generation remain unknown until separately approved
  service activation and gates.
- 32B current runtime feasibility remains unknown and must not be inferred from
  historical success.

## Status: APPROVED

Approved for implementation-only work on 2026-08-12. No provider call, endpoint
call, service start, weight load, publication, deployment or outreach is
authorized by this spec.

Round-2 implementation is code-complete under the same non-operational scope.
The 470-test affected/adjacent slice and static gates pass; the bounded full
suite timed out without a verdict. Independent terminal re-review and any live
route or local activation remain separate gates, so the candidate remains
quarantined and non-admitted.
