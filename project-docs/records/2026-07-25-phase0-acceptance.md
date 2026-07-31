# CC-1 Phase 0 acceptance record

**Date:** 2026-07-25
**Branch:** `feat/cc1-phase0-ground` (10 commits, off `feat/release-32b`)
**Plan:** [plans/2026-07-25-cc1-phase0-ground.md](../plans/2026-07-25-cc1-phase0-ground.md)
**Spec:** [specs/2026-07-25-certified-commons-design.md](../specs/2026-07-25-certified-commons-design.md)

**Verdict on the gate: PASS. `rewitness=MATCH`.** Under the plan's own rule,
Phase 1 may begin. Read section 5 before treating that as a result.

---

## 1. The gate

The plan's disproof condition was: take one existing orphan chain end to end
behind one command within a week, using only code that already existed. If that
could not be done, the premise was disproven for the price of a week.

```
$ python -m harness.cli_entry gate
  collect: group_size=4, temperature=1.0, estimator=drgrpo, n_pass=1,
           learnable=True, n_undecided=0, n_excluded=0,
           signal_hash=dda8a7414a71c071
  verify: verdict=PASS, output_hash=93e4b6c6b7a05c82, attribution=CANDIDATE
  seal: envelope_hash=1993af18b980c95d, claim_hash=23450831b0b42121
  rewitness: result=MATCH
verdict=PASS rewitness=MATCH
subject=1993af18b980c95d claim=23450831b0b42121 signal=dda8a7414a71c071
EXIT=0
```

**From a fresh `git clone --depth 1`, with no `pip install` of anything, on a
bare interpreter:** identical output, identical exit code, and byte-identical
digests (`dda8a7414a71c071` / `1993af18b980c95d` / `23450831b0b42121`). The
clone was made from the local repository over `file://`, so this establishes
clone-independence and determinism. It does not establish network-independence,
because the run was not executed with networking disabled; the CI `gate` job
runs the same command with no install step, which is the closer test.

**The gate was shown to fail before its pass was believed.** Editing the sealed
verdict from PASS to FAIL yields `DRIFT`. Replacing the candidate with an empty
triple list yields `DRIFT`. A missing envelope and a malformed envelope each
yield `UNVERIFIABLE`, never `MATCH`.

## 2. Test results, exact

| Suite | Command | Result |
|---|---|---|
| Phase 0 slice, 11 files | `pytest tests/test_verdict.py tests/test_oracle_verdict_widening.py tests/test_oracle_env_boundary.py tests/test_advantages.py tests/test_rl_group_sampling.py tests/test_rl_from_oracle.py tests/test_envelope_verdict_binding.py tests/test_envelope_interop.py tests/test_gateway_auth.py tests/test_gate_end_to_end.py tests/test_file_gate.py` | **85 passed, 1 skipped** in 1.23s |
| Reverse-import regression surface, 23 files | oracle conformance, hostile candidate, pytest-oracle-skip, exec oracle, kernel oracle, matmul, selector, consensus, calibration, integrity, quorum, escalation, failure corpus, chain, chain rewitness, verify receipt, proof cache, receipts ledger, file-backed store, grounding closure, transitive witness, adaptive select, gateway | **243 passed** in 201s |
| Verifier stdlib closure | `python scripts/check_verifier_stdlib.py` | 14 modules reachable from 9 entry points, **clean** |
| File gate | `python scripts/check_file_gate.py` | **15 grandfathered, 0 new, 0 grown** |
| Every module parses | AST-parse all of `harness/` | **clean** (after the BOM fix, section 4) |

The one skip is `test_token_file_is_not_world_readable`, which asserts POSIX
permission bits and is skipped on Windows by design. It runs on the ubuntu and
macos legs of CI.

## 3. Live defects closed, each with the test that would catch a regression

| Defect | Where it was | Regression test |
|---|---|---|
| GRPO groups sampled across nine temperatures including greedy `(0.0, 0)`, so the importance ratio was wrong for every member and the greedy member paid the policy to become deterministic | `rl_from_oracle.collect` via `budget_schedule` | `test_rl_group_sampling.py::test_every_rollout_in_a_group_shares_one_temperature`, `::test_no_greedy_sample_ever_enters_a_training_group` |
| UNVERIFIABLE was unrepresentable: `OracleResult.passed: bool`, `verdict()` returned only PASS or FAIL | `oracle.py` | `test_oracle_verdict_widening.py::test_passed_raises_on_a_non_dispositive_verdict` |
| UNDECIDED excluded from the gradient would have been a free escape hatch strictly better than failing | `rl_from_oracle` | `test_rl_group_sampling.py::test_undecided_is_loss_masked_with_zero_advantage_and_still_counted` |
| Harness bugs were scored against the candidate | `rl_from_oracle` | `test_rl_group_sampling.py::test_harness_attributable_failure_is_excluded_and_recorded` |
| `run_env()` handed the entire process environment to a subprocess executing model-written code | `oracle.py:33` | `test_oracle_env_boundary.py::test_a_secret_in_the_parent_environment_does_not_reach_the_child` |
| Gateway had no authentication while exposing keychain writes, MCP argv registration, package installs, and an edit-and-execute agent loop; `Host` was never validated | `gateway.py` | `test_gateway_auth.py::test_foreign_host_header_is_refused_even_with_a_valid_token` and 11 others |
| Nothing at the envelope level changed when a stored verdict was flipped | `envelope.py` | `test_envelope_verdict_binding.py::test_flipping_the_verdict_changes_the_claim_digest` |
| `harness/scaffold.py` carried a UTF-8 BOM and could not be AST-parsed, so it was invisible to every static check in the repository | `scaffold.py` | CI `parses` job |

## 4. Two places the plan was wrong, and the evidence that caught it

Recorded because a plan that is never wrong is a plan nobody checked.

**The receipt hash.** The plan said to bind the verdict into `content_hash`.
An existing test, `test_envelope_interop.py::test_verdict_does_not_change_the_content_hash`,
asserted the opposite as a deliberate property, and it was right:
`content_sha256` is the in-toto **subject** digest, and the verdict is a
predicate about that subject. Two verifiers reaching opposite conclusions about
the same task and candidate must still produce the same subject id, or their
disagreement cannot be located, and the in-toto and DSSE export would break.
Resolution: `content_*` stays verdict-free; new `claim_hash` / `claim_sha256`
bind the verdict. `chain.py` needed nothing, because `StageReceipt.receipt_hash`
already pops only `prev_hash`.

**The stdlib check.** The plan specified a blanket scan of `harness/` for
third-party imports. Running it flagged `serve.py` (torch, transformers, peft)
and `quant_dither.py` (numpy, scipy), neither of which is on the verifier path.
A check that flags them either fails forever or gets weakened into uselessness.
Resolution: walk the transitive import closure of the verifier entry points and
assert stdlib-only over that closure. Verified able to fail by injecting
`import numpy` into `advantages.py`, caught at `advantages.py:16`.

## 5. What Phase 0 does NOT prove

Stated plainly, because the acceptance of a green gate is exactly where an
overclaim would enter.

- **No model was trained. No weight moved.** `PolicyOptimizer` remains a
  Protocol with no implementation. There is no GRPO gradient step in this
  repository.
- **No uplift was measured**, and none can be until the optimizer, the control
  arms, and the preregistration exist. Nothing here bears on whether verified
  reward improves a model.
- **The gate contains no model at all.** Its proposer is a deterministic local
  function chosen so that the chain is under test rather than generation. It
  demonstrates that the parts compose. It demonstrates nothing about a policy.
- **Receipts are not signed.** No Ed25519, no key custody. `claim_sha256` is
  the value a signature should cover; nothing signs it yet. Every receipt is
  tamper-EVIDENT to an honest-but-careless party and forgeable by a motivated
  one.
- **The ledger has no inclusion or consistency proofs** and no external anchor,
  so append-only remains policy rather than a proven property, and a split view
  would be undetectable.
- **No stranger has re-derived anything.** CI on three operating systems is a
  mechanical stranger, not a human one, and it did not exist before today so it
  has not yet run on a pull request.
- **UNVERIFIABLE has no typed reason codes yet.** The verdict is representable;
  the spec's requirement that it say *why* is not implemented.
- ~~Task 11 of the plan is not done.~~ **Done (commit `254b09a`).** Both
  invariants are now frozen with tests, and both are in the CI matrix.
  Accept-path purity is verified able to fail by injecting history-dependence
  into `run_gate`. The Phase 0 slice is **93 passed, 1 skipped** as of that
  commit, superseding the 85/1 recorded in section 2.
- **The desktop app does not know about the gateway token.** Task 7 added
  authentication without updating the Flutter client, so the desktop app will
  receive 401s against a gateway started by `main()` until Phase 1 teaches it to
  read `FLYWHEEL_HOME/gateway.token`. This is a known, recorded break.
- **The 15 grandfathered file-gate violations are frozen, not fixed.**
  `gateway.py` is still 2,400 lines.

## 6. Verdict

The gate reaches MATCH from a clean clone with byte-identical digests, the
regression surface is green at 243 passed, and eight live defects are closed
with a named regression test each. Under the plan's stated rule, **Phase 1 may
begin.**

The honest scope of that verdict: Phase 0 proved that the existing parts compose
into a chain a third party can re-run, and that several things which would have
silently invalidated later results are now impossible. It proved nothing about
capability, nothing about uplift, and nothing about a model.
