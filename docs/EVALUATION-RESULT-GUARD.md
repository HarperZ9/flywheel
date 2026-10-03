# Evaluation result admission

An operator needs to know whether an evaluation report supports accepting its
observations or comparing its arms. Invocation success, an intact hash and a
model's completion claim do not establish that the objective was achieved.

`harness.evaluation_result_guard.check_evaluation(records, plan=plan,
authorities=authorities)` checks inert records against a controller-owned plan
and separately supplied observation authorities. It reuses the existing output
contract, METHOD mandate and critical-field HOLD behavior. This is a Python API;
it adds no executor, model call, command authority, network client or CLI route.

## Controller plan

The controller supplies a dictionary with exactly three keys:

| Key | Value |
| --- | --- |
| `trials` | Nonempty list, at most 4,096 planned trials. |
| `contrasts` | Unique condition names whose differences were declared before comparison; may include `method`. |
| `useful_defense_pairs` | List of `{evaluation: trial_id, benign: trial_id}` pairs, or an empty list. |

Every trial has `trial_id`, `task_id`, `attempt_id`, `arm_id`, `model_revision`,
`source`, `method`, `role` and `conditions`. The role is `evaluation` or `benign`.
Conditions name `task_revision`, `scoring`, `harness`, `budget`, `access` and
`safeguards`. Identifiers, revisions, methods, sources and condition values are
nonempty strings. These values identify the controller's definitions; this
adapter does not retrieve or validate the definitions they name.

Trial IDs must be unique. Each arm pins one model revision and covers the same
task/repetition matrix and roles. Model revisions may differ between arms.
Conditions and methods must match at corresponding task/repetition slots unless
the controller declared that dimension as a contrast. A declared contrast makes
the report eligible for that comparison; it does not establish causation.

A useful-defense pair requires a benign trial from the same arm. An independently
checked benign completion is necessary to admit that declared utility claim.
This does not prove defense effectiveness. When no useful-defense claim is made,
leave the pair list empty; a checked benign failure remains a valid observation.

## Submitted records and authorities

Each record has exactly `trial_id`, `source`, `method` and `observation`, plus
optional `labels` containing `provider` and/or `nation`. Labels do not affect the
result. An observation contains exactly these fields:

| Field | Meaning |
| --- | --- |
| `origin` | `observed`, `reported`, `simulated`, `attempted`, `unsupported` or `missing`. |
| `outcome` | `completed`, `not_completed` or null. Observed outcomes must be non-null. |
| `value` | Exact JSON scalar or null; no nonfinite numbers or nested objects. |
| `reason` | String; required and nonempty for unsupported or missing observations. |
| `model_revision` | Must match the controller's pinned arm revision. |
| `conditions` | Must match that planned trial's conditions. |

Unsupported and missing observations require null outcome and value. Simulated,
reported and attempted completions may be faithfully reported, but cannot count
as checked executed completions. Extra trust flags, invocation hashes and tool
payloads do not belong in this schema. Keep them in the source receipt archive.

The controller passes `authorities` as a dictionary from source ID to a read-only
callable. Each callable receives a detached copy of its planned trial and returns
an observation in the same shape. It receives no submitted answer. The controller
must select an independent observation source, not a resolver that copies the
claim. The adapter cannot prove resolver independence or honesty.

The adapter copies and validates plain JSON inputs before calling authorities.
It checks the entire observation using an exact canonical JSON comparison, so
booleans cannot equal integers and omitted provenance cannot silently pass.
Method and citation requirements apply even when the submitted value is right.
Missing authorities, exceptions and malformed responses hold the report.
Diagnostics omit observation payloads, expected values and exception details.

Resolvers are trusted application code and must be bounded and read-only. This
synchronous API cannot cancel a blocking callable or sandbox its side effects.
Malformed or oversized JSON inputs are refused before authority calls.

## Reading the result

Read the top-level `release`, not only `fidelity.release`. Fidelity can pass for
an accurately reported simulation while completion admission remains HOLD.
Missing, extra, duplicate or malformed trials hold before authority calls.
Such a report has null counts rather than an invented zero denominator.

`arms[arm_id][role]` keeps evaluation outcomes and benign utility separate. Each
group has planned attempts, checked observed attempts, checked completions,
unavailable attempts, distinct tasks and `task_clusters` mapping task IDs to
planned repeat counts. A descriptive attempt completion rate is null if any
outcome in that group is unavailable. Repeated attempts are not independent tasks.
Top-level attempt and task counts describe evaluation trials; separate benign
counts and the total submitted-record count preserve the rest of the denominator.

No confidence interval, causal conclusion or cross-arm ranking is calculated.
RELEASE means the report passed this admission contract. It does not authorize
publication or establish event truth, model safety, generalization or superiority.

## Validation and release boundary

The deterministic tests cover checked benign completions, repeated tasks, wrong
values and methods, absent authority, invalid trial sets, simulation, unsupported
conditions, label invariance and failed benign utility. Run:

```sh
python -m pytest tests/test_evaluation_result_guard.py tests/test_evaluation_result_boundaries.py
```

This adapter is an unreleased candidate. Existing release pins, executors and
published evaluation results are unchanged. Its immediate benefit is a stricter
consumer boundary for unsupported success claims; its remaining dependency is
the controller's independently justified plan and observation authorities.
