# Flywheel harness: an architecture map

`harness/` holds roughly 860 Python modules. About 790 sit flat at the top
level, and the rest live in a few subpackages (`certificates/`, `criteria/`,
`crypto/`, `domain_packs/`, `governance/`, `infra/`, `writing_lint/`). A flat
tree of that size is hard to enter cold, so this file groups the load-bearing
modules by the job they do and names a reading order for someone taking the
code over.

This map covers the modules a new developer needs first. It is not a full
index. When a description here and the code disagree, the code wins, and a
correction to this file is welcome.

## Start here

Read these seven in order. Together they show what "accept" means, how a run
produces a checkable record, and how a command reaches the engine.

1. `oracle.py`: the verifier adapter. It defines what it means to accept, and
   it states the C2 invariant: the oracle is the only thing that accepts, and
   no learned model sits on the accept path.
2. `verdict.py`: the verdict vocabulary. Verdicts are four-way (pass, fail,
   unverifiable, undecided) with an execution state and an attribution, so a
   run that did not decide is never scored as a failure.
3. `gate.py`: the Phase 0 disproof gate. One command runs the whole chain end
   to end. An exact oracle disposes candidates, a group is scored, the winner
   is sealed into an envelope, and the envelope is re-witnessed. No model runs
   in this gate.
4. `acceptance_criteria.py`: how a "done" claim is kept honest. A criterion
   starts failing and only a named oracle can flip it, so an agent reporting
   "done" and a criterion reading "passing" stay two separate facts.
5. `why.py`: how a verdict is explained from the record alone, offline, with
   no model and no network.
6. `lanes.py` then `lane_runtime.py`: the lane layer. This is the roster of
   tool servers and the runtime that decides how each one launches.
7. `cli_entry.py`: how the `flywheel` command dispatches to all of the above.

## The accept path, the oracle, and the gates

This is the core the whole engine defends. The rule that a verdict depends only
on inputs, oracle version, and config lives here, and `tests/test_accept_path_
purity.py` checks it by replay and by import closure.

| Module | Role |
| :-- | :-- |
| `oracle.py` | The verifier adapter and the C2 invariant. `PytestOracle`, `StubOracle`, `OracleResult`, `canonical_hash`. |
| `verdict.py` | The four-way verdict, execution state, and attribution. |
| `task.py` | The `Task` record a candidate is verified against. |
| `acceptance_criteria.py` | Criteria only a named oracle can flip. One mutation site, enforced by a test. |
| `gate.py` | The disproof gate: oracle, group, receipt, re-witness, no model. |
| `matmul_oracle.py` | The exact symbolic checker the gate uses. It never executes candidate code. |
| `rl_from_oracle.py` | Collects a scored group of rollouts from the oracle. |
| `advantages.py` | The group-relative estimator, recorded in receipts. |
| `proc_kill.py` | `spawn_killable` and tree-kill, so a hostile candidate costs one timeout. |
| `junit_report.py` | A fresh JUnit report per pytest run, and `grade`: exit 0, one pass or more, and no failed, skipped or xfailed test. |
| `workdir_restore.py` | Puts the task workdir back after every oracle and witness run, so a file one candidate writes cannot grade the next. |

## The lane system

A lane is one MCP tool server the gateway can launch. The lane layer is the
flagship tool family, and it decides which lanes exist and how each one starts.

| Module | Role |
| :-- | :-- |
| `lanes.py` | The lane roster and its registry: `LANES`, `lane_roster`, `lane_report`, `install_lane`. |
| `lanes_registry.py` | The `Lane` dataclass and its kinds (pip, npm, bundled, http). |
| `lane_runtime.py` | Runtime selection: the auto, source, and package profile system. |
| `lane_runtime_support.py` | The pure, side-effect-free helpers `lane_runtime.py` calls. |
| `lane_runtime_versions.py` | Version validation shared across the runtime path. |
| `bundled_lane_admission.py` | Admits the relay lane carried inside a frozen build, only when its source manifest matches the descriptor. |
| `bundled_lane_expectations.py` | The expected descriptor a bundled lane is checked against. |
| `mcp_client.py` | `LaunchSpec` and the MCP client the gateway launches lanes with. |
| `lane_caller.py`, `lane_call_route.py` | Calling a lane and routing the call. |

## The gateway

The gateway is the server that holds grants, custody of secrets, and the agent
execution surface. It is the largest family in the tree, so the entries below
are the doors into it. The family holds many more modules than these.

| Module | Role |
| :-- | :-- |
| `gateway.py` | The server entry point (`main`). |
| `gateway_auth.py` | The auth check. It is on the offline verifier path. |
| `gateway_operations.py`, `gateway_operation_route.py` | Operation shape, validation, and routing. |
| `gateway_agent_execution.py`, `gateway_agent_grant.py` | The agent run surface and its grants. |
| `gateway_agent_mcp_admission.py`, `gateway_agent_mcp_route.py` | Admitting and routing MCP tool calls for an agent. |
| `gateway_grant_index.py`, `gateway_grant_inbox.py` | The grant store and its inbox. |
| `gateway_custody.py`, `gateway_secret_boundary.py` | Secret custody and the secret boundary. |
| `relay_bridge.py` | The `remote` and `relay` commands. |
| `oauth_signin.py`, `oauth_service.py` | OAuth sign-in for the gateway. |

## Verification and receipts

Everything a stranger re-derives to check the work. These modules are the
offline verifier path, and `scripts/check_verifier_stdlib.py` asserts they
import nothing outside the standard library.

| Module | Role |
| :-- | :-- |
| `receipt.py` | The record a stranger re-derives, with its denominator. |
| `envelope.py` | The proof envelope a candidate is sealed into. |
| `chain.py` | The tamper-evidence chain over the log. |
| `witness.py`, `byte_witness_verify.py`, `action_witness.py` | Re-witnessing a run, its bytes, and its action log. |
| `merkle.py` | The tree a stranger recomputes. |
| `ledger.py` | The receipt log and its inclusion proofs. |
| `bundle.py` | What a stranger is handed and checks. |
| `receipt_sign.py`, `ed25519_verify.py` | Signing and the signature check a stranger runs. |
| `anchor.py`, `ots_verify.py` | Ties a signed head to a timestamp, and the OpenTimestamps proof back to Bitcoin. |
| `audit_receipt.py`, `usage_receipt.py` | The Layer-2 audit and usage-metering receipts. |
| `contest.py` | How a stranger disagrees on the record. |
| `why.py` | Answering "why was this accepted?" from the record. |
| `evidence_json.py` | Canonical JSON bytes and sha256, shared across receipts. |
| `certificates/` | The certificate checkers (base, zarankiewicz, independent, crossing, generators). They are the accept path for the construction families. |

## Benchmarks

The benchmarks measure a claim and record it with its denominator and its
does-not-prove. They are not on the accept path.

`accountability_bench.py`, `agent_recovery_bench.py`, `governed_agent_bench.py`,
`science_bench.py`, `source_mined_bench.py`, `trace_bench.py`, `uplift_bench.py`,
`verified_bench.py`, `receipting_cost_bench.py`, and `classifier_friction_bench.py`.
Shared plumbing lives in `benchmark_hygiene.py` and `benchmark_receipts.py`.

## Command-line entry points

| Module | Role |
| :-- | :-- |
| `cli_entry.py` | The `flywheel` console command. Dispatches umbrella commands, packaged commands, and passthrough to the front controller. |
| `cli.py` | The task runner: `py -m harness.cli <task_dir>`. Runs the harness on a task and writes the envelope. |
| `scripts/run_harness_cli.py` | The front controller `cli_entry.py` hands passthrough commands to. |
| `acp_cli.py`, `dap_cli.py`, `lsp_cli.py`, `packs_cli.py`, `evidence_cli.py`, `writing_cli.py`, `governance_cli.py` | Packaged subcommands that run from a bare install without a source checkout. |

## The classifier, fenced off the accept path

`classifier_model.py` is a deliberately weak, uncalibrated baseline scorer. It
is kept off the automatic accept path by the C2 invariant in `oracle.py`. Its
sibling modules (`classifier_features.py`, `classifier_training.py`,
`classifier_calibration.py`, `classifier_cli.py`) build and score it, and its
own docstring and `DOES_NOT_PROVE` constant state what a score does not
establish. The model can rank candidates. It cannot accept one.

## Where the "why" lives

Four modules carry the reasoning the rest of the tree assumes. Read their
docstrings when a design choice is not obvious from the code around it.

- `oracle.py`: the C2 invariant and the determinism contract.
- `acceptance_criteria.py`: the single-mutation-point discipline for criteria.
- `gate.py`: why the disproof gate has no model and executes no candidate code.
- `why.py`: the practitioner contract, where doubt is answered with records.

Two scripts guard those choices in continuous integration:
`scripts/check_verifier_stdlib.py` keeps the accept path stdlib-only, and
`scripts/check_file_gate.py` holds every source file to 300 lines. `CONTRIBUTING.md`
lists the full set of gates and how to run each one locally.
