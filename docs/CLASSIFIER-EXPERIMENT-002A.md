# Classifier Experiment 002A: changing action menus

Status: executed local synthetic diagnostic, September 17, 2026. This is a
workflow evaluation slice, not architecture selection or production acceptance.

## Decision and result

Do not integrate the frozen Experiment 001 weights into this form-action domain.
Retain the rule baseline for fully specified structured policies. Develop suitable
outcome-labeled data before comparing new classifier heads, and use a fresh
holdout for any subsequent improvement claim. Automatic selection stays disabled.

| Policy | Cases | Completed forms | Justified blocks | Unresolved at step limit |
| --- | ---: | ---: | ---: | ---: |
| Deterministic exact-policy baseline | 10 | 9 | 1 | 0 |
| Frozen CPU classifier | 10 | 0 | 0 | 10 |
| Frozen encoder classifier | 10 | 0 | 0 | 10 |

Nine cases are feasible; one has an unavailable requested destination. A
justified block is appropriate handling of that case, not a completed form.
All ten cases remain in the completion denominator. The submitted-artifact
checker labels episodes without a terminal submission or block as `unknown`;
the runner records their observed noncompletion and exhausted 12-step budget.

Both learned policies returned validated scores on all their 120 decisions.
Neither run failed because its scorer was unavailable. The bundled tokenizer
check found no input over the encoder's 256-token bound: across the three main
arms' 271 decisions, maximum state length was 180 and candidate length 25.

These heads were trained for routing/tool/context/escalation diagnostic labels,
not the new form-action domain. The result rules out naive integration of these
weights here. It does not establish a general architecture ranking, a competitor
comparison, or that training on relevant outcomes cannot improve performance.

## Method

The owned environment is an in-memory travel-search form with no browser, account,
network or booking. Ten authored cases cover corrections, stale and disabled
choices, an absent destination, one transient submission failure, and page text
that conflicts with the user goal. Menus use changing opaque IDs. Each policy
acts on its own resulting state rather than receiving a successful replay path.

Rules and learned policies see the same public request, current fields and
eligible menu. The rule parses the explicit structured policy. The learned
policies use their frozen `tool_selection` head with experimental argmax; this
does not enable real tool execution or calibrated automatic selection.

Seed: 1709. Budget: 12 actions per episode. Neural embedding cache clears between
episodes and may reuse text within an episode. All cases and source hashes are
recorded in each report. These cases are now development evidence because their
outcomes have been inspected.

Model load is separate from episode timing. The CPU model loaded in about 23 ms;
the encoder loaded on an RTX 4090 in about 6.71 s. Across ten episodes the recorded
elapsed times were about 143 ms and 2.11 s respectively. These are single-pass
simulator timings on shared hardware, including unsuccessful episodes. They
exclude browser acquisition, model download, artifact serialization and human
work. No useful-work speedup follows from them; energy and monetary cost are null.

## Check the measurement

Review found and corrected flaws before learned-model execution:

- Submit eligibility originally depended on matching the correct answer. It now
  depends on ordinary form completeness, allowing the independent checker to
  detect a wrong submission.
- Some intended feasible cases lacked required controls/defaults. Those were
  repaired before comparison, and state text was compacted to fit the encoder.
- Runtime failure or unavailable scores could become an apparent justified
  block. Such failures now execute no action and cannot acquire a success verdict.
- Snapshot identity and terminal evidence were under-validated. The checker now
  binds the case, goal, expected fields and terminal operation/form, while an
  available-target control catches falsely justified blocks.

The final recorded actions were re-executed without model calls in the same
simulator, then separately checked. Source hashes matched. Controls confirmed
ordinary success, rejection of a wrong submitted city, and unknown outcomes for
a different case or missing submit evidence. This re-derives artifact/state
consistency; it does not independently reproduce neural inference, authenticate
historical execution, validate timing, or establish real-browser usefulness.

## Reproduce

Use the frozen artifacts described in [Experiment 001](CLASSIFIER-EXPERIMENT-001.md)
or explicitly report newly trained artifacts as a different experiment. The
encoder needs its optional training/runtime dependencies; the fixture, CPU model
and outcome checker are standard-library code.

```text
python -m train.classifier_workflow_experiment --kind rules --seed 1709 --max-steps 12 --out NEW_RULES_DIRECTORY
python -m train.classifier_workflow_experiment --kind baseline --artifact CPU_MODEL_JSON --seed 1709 --max-steps 12 --out NEW_CPU_DIRECTORY
python -m train.classifier_workflow_experiment --kind encoder --artifact ENCODER_ARTIFACT_DIRECTORY --device cuda --seed 1709 --max-steps 12 --out NEW_ENCODER_DIRECTORY
```

Every output directory must be new. Reports contain the cases, source hashes,
model identity, action requests/results, scores, final snapshots and checks.
The learned-model commands also run the rule comparator. Focused regression
coverage lives in `tests/test_classifier_workflow_experiment.py` and
`tests/test_classifier_workflow_policy.py`.

Still open: architecture ablations, relevant-data training, grammar-constrained
generation and shared-prefix comparators, real DOM extraction, independent
workflow task sets, calibration, and any deployment or superiority claim.
