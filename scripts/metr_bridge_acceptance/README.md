# METR task bridge interoperability

This acceptance workflow checks whether a real METR task-image run can produce
Inspect evidence that Flywheel retains without turning a reported score into
independent verification. It does not measure model capability or certify METR
Task Standard conformance.

The GitHub workflow builds the upstream `count_odds` task and its OCI task-info
artifact, keeps both in a registry on the runner's loopback interface, and runs
three deterministic solvers through the real bridge:

- The correct answer, `6`, must score `1`.
- The wrong answer, `1`, must score `0`.
- A response without a submit tool call must not score `1`. The bridge treats
  completion text as a fallback answer, so this is not a no-answer control.

Every control must observe the expected task, sample, scorer, no-model runtime,
and successful evaluation status. Missing, non-finite, incorrectly named or
non-numeric scores fail the control. Runtime failures remain failures even when
they occur in a negative control. All controls write a summary before the job
decides whether it passed.

## Run and inspect

The path-filtered pull-request workflow is `.github/workflows/metr-task-interop.yml`.
It can also run through workflow dispatch once present on the default branch.
It requires an Ubuntu runner with Docker; local classifier checks require only
Python:

```sh
python -m unittest discover -s scripts/metr_bridge_acceptance -p 'test_*.py'
```

For task execution, the workflow checks out pinned bridge and Flywheel source,
installs the bridge's locked environment, verifies the actual Inspect no-model
runtime, builds the upstream image, and invokes `run_count_odds_controls.py`
with `IMAGE_TAG` and `RECEIPTS_DIR`. Its solver never calls model generation;
Inspect's `NoModel` raises if generation is attempted. No provider keys are
needed or supplied.

Retained artifacts include source revisions and hashes, actual dependency
versions, image manifests, task metadata, native `.eval` logs, JSON exports,
per-control results, and Flywheel import outputs. Import outcomes preserve
complete, incomplete, rejected and tool-error states. Inspect's scorer remains
the reporting authority for its score; Flywheel's byte witness does not endorse
the score or the task's design.

## Limits

The workflow is an interoperability experiment until its actual run artifacts
establish the outcome. Pure classifier tests are not task-image acceptance.
Task, scorer, bridge and runtime share upstream dependencies; these are not
independent implementations. A binary arithmetic task does not validate a broad
security evaluation or a claim about an agent's disposition.

The image build obtains system packages from upstream repositories. Recorded
versions and digests identify the observed environment but do not guarantee
bit-for-bit rebuilds from mutable system-package sources.

The bridge repository had no detected license at the pinned revision. The
workflow does not redistribute its source or built images; its registry is local
to the disposable runner. Receipts retain source URLs and hashes. Review the
licensing and evidence-sharing scope before distributing additional material.
