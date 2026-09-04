# Cross-harness head-to-head, 2026-09-03: the denominator, and why it was two

Run: `hh-focused-20260903-194505`, focused-run phase, five provider roles across
the fourteen tasks of `flywheel_agentic_gauntlet_v1`, one repetition each.

## What the run produced

| count | meaning |
| --- | --- |
| 70 | attempts collected |
| 20 | reached a provider (`launched`) |
| 50 | discarded before any provider was called (`blocked`) |
| 2 | returned a parseable result |
| 0 | passed an oracle |

The run is 70 attempts and not 84. Five roles execute, not six: `dry` is listed
in the contract but has no branch in `build_adapter_registry`, so it plans and
never runs. Five roles times fourteen tasks times one repetition is 70. Any
figure quoting 84 for this run is wrong.

Billed cost across the 20 launched attempts was $0.3402, all of it on
`claude_code`. Wall clock was 1694 seconds. The other four roles report
`provider_reported_cost_usd` of zero, which is a missing measurement rather than
free inference: the Codex CLI and the Ollama endpoint do not report a cost and
the adapter records what it is given.

Observed models: `claude-sonnet-5` for `claude_code`, `gpt-5.3-codex-spark` for
both `codex_harness` and `flywheel_harness`, `flywheel-local-coder-14b` and
`flywheel-local-coder-32b` for the two local roles.

## Finding one: a contract seam discarded fifty attempts

Every one of the 50 blocked attempts carries the same shape of failure detail:

```
required input invalid: operator://local-model-base-root          (20)
required input invalid: workspace://public/forum/src/forum/ledger.py  (5)
required input invalid: workspace://public/mneme                  (5)
required input invalid: workspace://public/relay                  (5)
required input invalid: workspace://public/plexus                 (5)
required input invalid: operator://opencode-installation-root     (5)
required input invalid: external://project-docs/records           (5)
```

Every target named there exists on disk. The tasks were not wrong. Two halves of
one contract disagreed about what a required input is.

`harness/cross_harness_manifest.py::_input_hashes` understood the three schemes,
accepted a typed reference, deliberately recorded no hash for it, and moved on.
`harness/cross_harness_artifacts.py::create_attempt_workspace` then called
`_safe_relative` on the same string, which rejects anything containing a colon,
because on Windows a colon is a drive letter and an alternate data stream
marker. The manifest said the reference was legitimate. The workspace builder
said it was invalid. The attempt died between them, and the receipt recorded
`required input invalid`, which reads like a bad task.

Ten of the fourteen tasks carry at least one typed reference. Ten tasks times
five roles is 50, which is the whole blocked set.

### The fix

`harness/cross_harness_input_refs.py` is now the single authority both halves
call. `classify_reference` returns a scheme and a payload, `partition_inputs`
splits declared inputs into what a sealed workspace can hold and what it cannot.
Nothing became more permissive: a typed reference is still never copied into a
workspace, the payload rules are the ones the manifest already enforced, and a
task with a registered oracle checker still may not declare one. The change is
that such a reference is now reported as declared and not provisioned, instead
of aborting the attempt.

## Finding two: a bounded-output check discards the evidence it rejects

Four of the 20 launched attempts recorded no raw output at all. Not an empty
file, no file:

| attempt | failure | cost | wall |
| --- | --- | --- | --- |
| `claude_code/agt-001` | `malformed_jsonl` | $0.1398 | 95.4s |
| `claude_code/agt-010` | `malformed_jsonl` | not reported | 352.3s |
| `codex_harness/agt-010` | `malformed_jsonl` | not reported | 41.1s |
| `flywheel_harness/agt-010` | `malformed_provider_output` | not reported | 83.0s |

`claude_code/agt-001` ran five provider turns and produced 10,421 output tokens,
which the usage block records. The receipt keeps the token counts and the cost
and drops the text. When `provider output was not bounded UTF-8 JSONL` fires,
`raw_output_path` is left empty and the bytes are gone, so a paid attempt leaves
no evidence of what the model actually said. The bound should be enforced by
truncating and recording the truncation, not by discarding.

Both local roles wrote raw output for `agt-010`, so this is specific to the
three CLI-backed adapters rather than to the task.

## Finding three: the scorable set is four of fourteen

Only four tasks carry a non-empty `oracle` block: `agt-001`, `agt-003`,
`agt-009`, `agt-010`. The other ten declare no checker, so a run of them
produces output that nothing in the repository can read. That limit is
independent of whether they launch.

Before the fix, the executable set and the scorable set coincided exactly, and
not by accident. `PILOT_TASKS` in the manifest binds each registered checker to
one canonical task and refuses a typed reference on any of them, so the four
scorable tasks were precisely the four with no typed reference, which were
precisely the four that survived the workspace builder.

After the fix the two numbers separate, which is the point:

```
provisionable: 14 of 14
scorable:       4 of 14
measured:       4 of 14
```

## The gate that would have caught this for free

`harness/task_set_executability.py` and `flywheel task-set-executability` answer
both questions about a task set before a run, reading the repository and calling
no provider. It reports per task whether every declared input resolves, whether
a registered checker and its fixture exist, and which blockers apply. The verdict
on the shipped set is `TASK_SET_PARTIAL`.

Nothing in the repository asked these questions before. The manifest build
hashes inputs and never tries to seal a workspace, so it could not have found
the seam, and it has no view of the oracle registry, so it could not have found
the missing checkers.

## What this does not prove

- The two attempts that returned both failed with the same single code,
  `failure_classes_mismatch`. Two attempts is not a measurement of either
  harness, and no comparative claim is made here.
- The typed-reference fix makes ten more tasks reach a provider. It does not
  make them scorable, and it does not deliver the referenced material into the
  sealed workspace. Those attempts will run without it and should be read with
  that in mind.
- `agt-003` failed on `codex_harness` with a JSON envelope truncated at column
  2642. That is model-side truncation, not a harness defect, and it is not fixed
  here.
- The cost figure covers one role. Four roles report no cost, so $0.3402 is a
  floor on what the run cost, not the total.
- `snapshot_source_tree` hashes 41,040 files and 4,016 MB twice per run, and
  discards the whole run if the tree changes underneath it. `desktop/` alone is
  3,566 MB of Flutter build output. That is unaddressed.

## Reproduce

```bash
python scripts/run_task_set_executability.py --markdown-out task_set_executability.md
python -m pytest tests/test_task_set_executability.py tests/test_cross_harness_input_refs.py -q
```
