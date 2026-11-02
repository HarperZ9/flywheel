# studyrun: preregister, run, control, score, ledger

`harness.studyrun` runs one study end to end. It writes the preregistration and its sha256 before any run, hashes every input and code file, runs the analysis and its controls, checks every hash again, scores the verdict rules, writes a manifest and appends one ledger entry. Nothing is scored if the preregistration, the plan, an input or a code file changed during the run.

```bash
python -B -m harness.studyrun check  study/spec.json    # spec shape and preregistration anchors; runs nothing
python -B -m harness.studyrun prereg study/spec.json    # write PREREG, its .sha256 sidecar and prereg.lock.json
python -B -m harness.studyrun run    study/spec.json    # run, score, write the manifest, append the ledger entry
python -B -m harness.studyrun check  study/spec.json --result RESULT.json   # also resolve every verdict path on a result
python -B -m harness.studyrun audit  study/spec.json [--result RESULT.json] # limits, constants and post hoc files, any time
```

Exit codes: 0 scored (and reproduced, when the spec asks), 2 blocked or a bad spec, 3 a reproduction mismatch, 4 an autocheck failed. Exit 4 happens only for specs that declare limits, constants or post hoc files, or use `studyrun.spec/2`.

## The spec

A spec (`studyrun.spec/1`) names the preregistration, the inputs, the code, a seed, one analysis unit, its controls, the verdict rules and the ledger entry. A unit is `path/to/file.py:function`; the stage never knows what a unit computes.

- `analysis(ctx) -> dict`, where `ctx` holds `params`, `rng`, `seed`, `inputs`, `state` and `spec_id`.
- `control(ctx, analysis) -> list` or `{"null": list, "meta": dict}`. The stage summarises the null with `p = (count(null >= real) + 1) / (n + 1)` and reports a control unusable when it has fewer than `min_n` values or no spread, because a control that cannot fail proves nothing.

`tests/fixtures/studyrun/toy.py` is a worked pair: a two-group mean difference with a label-shuffle control.

## Rules the stage enforces

- **Preregistration first.** The PREREG text is never rewritten. The lock freezes the plan (analysis, controls, verdicts, seed) by `plan_sha256`.
- **Truth anchor.** A spec that scores an update-size metric (transfer entropy, a weight-change norm) must also score a truth-anchored measure (accuracy, return, target choice). Update size says how far a learner moved, never whether it moved toward the truth. The rule runs when a new lock is written (`anchor.py`).
- **Bounds.** `harness.studyrun.bounds.violations` gives exact one-sided binomial p-values with a Holm, Bonferroni or Benjamini-Hochberg family correction. It is tested against the shared CC0 stats vectors in `tests/data/stats_vectors.json`.
- **No bytecode beside read-only code.** A run that writes `__pycache__` next to the code it read is blocked.

## Power, planted truth, autochecks and forecasts

Each of these is optional under `studyrun.spec/1` and required under `studyrun.spec/2`.

- **Verdict paths with a dot in a key.** Escape the dot as `a\.b` (`a\\.b` inside JSON), or give the path as a list. A path that resolves nowhere names the dotted key and the fix, and the verdict stays UNTESTABLE: the reader never guesses.
- **Power gate.** With a `power` section, the lock applies the locked verdict rules to simulated runs and records each verdict's pass rate, a Wilson interval and whether it binds. A verdict under the bar is reported as non-binding in the result, the CLI and the ledger. A verdict path that resolves in no simulated run refuses the lock.
- **Planted truth.** With a `planted` section, the lock fits the sign and relative size of each lagged term on a calibration panel that is not a test input, or takes a cited prior fit, and refuses a truth world that plants a sign against the fit or leaves out a measured term. `{"none": "reason"}` says the study plants nothing.
- **Autochecks.** At lock, at the end of a run and on `audit`: each limit line is reread against its cited span and must still be in its record; each constant must be derived by a file that is not study code; each post hoc file is sealed by hash with its checkpoint, and an unregistered post hoc file is reported.
- **Forecasts.** `forecasts.verdicts` is scored by Brier and log score per verdict, with UNTESTABLE not scored. `forecasts.quantities` gets interval coverage, absolute error and the log10 miss factor. Scores go to `result.json`, the CLI and a ledger line.
- **Frozen with the plan.** New locks carry `ext_sha256` over `power`, `planted` and `forecasts`, hashed under the lock's canonical form. Adding those fields after the lock, or changing the simulations or calibration file, blocks the run. `limits`, `constants` and `posthoc` stay unfrozen, since adding them only adds checks.

Specs and locks written before these fields existed run and verify as before.

## Hashes

New locks and manifests are hashed under `canonical-record/1` (`docs/spec/canonical-record.md`) and say so in a `canonical_form` field. A lock with no `canonical_form` was written by the first prototype (2026-10-29) with `json.dumps(sort_keys=True)`, and it is verified under that form, so no existing lock stops verifying.

## What it does not do

studyrun checks that a study ran as it was frozen and that its controls could have failed. It does not judge whether the analysis answers the question, whether the inputs were the right ones, or whether a result holds outside its data.
