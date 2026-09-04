# Flywheel

Agent and contributor instructions for the Flywheel monorepo. This file is
self-contained: it names no local path and assumes no parent directory,
because this repository is published and cloned on its own.

## What this repo is
One platform, both halves:

- `harness/` is the Python engine: the verification harness and its evidence
  layer, the certificate families (Zarankiewicz, rectilinear crossing, matmul),
  the pool-and-arms measurement apparatus, the receipt / ledger / bundle stack,
  and the lane surface in `harness/lanes.py`. Zero runtime dependencies is a
  load-bearing invariant, and the verifier path is stdlib-only with a gate that
  proves it.
- `desktop/` is the Flutter native client (its own instructions live in
  `desktop/CLAUDE.md`). It renders the engine and never reimplements it.
- `site/` is the dev/CI fallback browser shell, served by the gateway.

This repository is the engine's canonical home. Its predecessors,
`HarperZ9/local-model` (engine) and `HarperZ9/flywheel-desktop` (client), are
archived and read-only; nothing lands there.

## Shipping surfaces (one version, one tag)
- PyPI: `flywheel-verify`, the engine; installing it puts the `flywheel`
  command on PATH. Published by `.github/workflows/publish.yml` on a `v*` tag
  via Trusted Publishing.
- Windows installer: built by `.github/workflows/desktop-release.yml` on the
  same tag, engine frozen from this repo, SHA-256 receipt attached to the
  GitHub Release.
- `pyproject.toml`, `desktop/pubspec.yaml`, and `desktop/lib/version.dart`
  declare one version; `tests/test_version_alignment.py` fails on drift.

## Gates that must stay green (run before a commit that touches them)
- `python scripts/check_file_gate.py`: no file over 300 lines. The burn-down only shrinks.
- `python scripts/check_verifier_stdlib.py`: the accept path imports no third party.
- `python scripts/check_claim_language.py`: no optimality claim on a public surface.
- `python scripts/check_public_instructions.py`: published instruction files stand alone.
- `python -m harness.cli_entry gate`: the disproof gate reaches PASS / rewitness MATCH.
- `python -m pytest tests/ -q`: the full suite. CI runs a curated slice plus the
  whole suite; a slice cannot catch a regression in a file it does not name, so
  the whole-suite job is the real gate.
- `flutter analyze` and `flutter test` in `desktop/` for client changes; CI
  runs them path-filtered (`desktop-ci.yml`).

## Invariants
- No learned model on the accept path. A checker decides; a model never does.
- No receipt, no accept. Every result carries its denominator, coverage, and
  `does_not_prove`. Nulls are published, not edited out.
- Every checker verifies a SUBMITTED object; none decides optimality.
  `NOT_PROVES_OPTIMALITY` travels on every certificate result, and the claim gate
  enforces it on public surfaces.
- A new certificate family needs a second, independently written checker before
  any selection comparison on it is two-sided.
- Truth over approval. Verify a specific claim or label it high / moderate / low /
  unknown. "Unknown" beats a plausible fabrication.
- A value an answer states is bound to the source that decides it, or it is
  labelled unchecked. Agreement with no source named is `UNVERIFIABLE`, not a
  pass. Rechecking your own arithmetic is not a check.

## Validating an answer before it reaches a reader
A model that rechecks its own work re-derives the same wrong number. The case
this was built from is public: a frontier demo filled out a Form 1040 and took
the tax from the rate schedule, which gives $4,165.50, where the form requires
the tax table, which gives $4,169. The arithmetic was right both times. What was
wrong was which source got to decide.

So the check runs against an authority, not against the reasoning:

```bash
flywheel check-output --contract task.contract.json --answer answer.json --allow-commands
```

From a checkout, `python scripts/run_output_check.py` takes the same flags.

- Exit `0` every field agrees with its authority and names it. Exit `1` a field
  disagrees. Exit `3` nothing confirmed a field, so it is unchecked, not wrong.
- Read the `next` block and go to the source it names. The report never carries
  the authoritative value, so an attempt that copies a number out of its own
  failure report has consulted nothing and will not pass.
- Command authorities do not run without `--allow-commands`. Without the grant
  the field comes back unchecked, which is the safe direction and not a passing
  one.
- Stop after two attempts that fail the same way. A third is a reroll, not a
  retry.
- Emit an answer that never validated, and emit it with the reason. Dropping it
  hides the work. Emitting it clean is the failure this exists to prevent.
- Read the `release` line as well as the verdict. `HOLD` means a field
  disagreed or a critical field went unchecked, and the answer does not ship.
  `--strict` puts that on the exit code.
- `--answer` reads Markdown, LaTeX, and Flywheel PDF as well as JSON, from a
  `flywheel-answer` fence, a `flywheelanswer` environment, or the attached
  stream. Prose is never mined for values. `--report review.pdf` writes the
  report back out in the format the suffix names.
- `--lean Answer.lean --verify-lean` emits the check as a Lean 4 file and runs
  the kernel on it. Read `#print axioms confirmed`: it names everything the
  result rests on, and `sorryAx` in that list means an obligation did not
  close. A kernel that refuses what the report passed takes the exit code with
  it. Without Lean installed the proof is `UNVERIFIABLE`, never `PASS`.
- For a financial, medical, or legal answer, name a domain pack and use its
  templates rather than inventing field shapes. `flywheel packs` lists them. A
  pack holds no domain data, so the authorities are still yours to supply.
- Three domains ship and the defect reaches many more. For a domain that does
  not ship here, write the pack as a `flywheel.domain-pack-declaration/v1`
  document and pass its path anywhere a pack name goes. A declaration may not
  carry a value, so a `maximum`, a `rate` or a `table` inside it is refused,
  and every template has to say what it catches.
  `examples/output-validation/water-treatment.pack.json` is a worked one.
- Add `--scope task|goal|session --subject <id>` to record the check. The
  end-of-session question is what went out unverified across the whole run, and
  the last check alone does not answer it.

In Python the loop is `harness.validated_answer.run_validated(produce, contract,
authorities)`, which produces, checks, hands the unresolved fields back to the
producer, and stops on a pass, on a repeated failure signature, or on running
out of attempts. Inside the harness loop, pass `output_contract` and
`output_authorities` to `run_loop` and a held answer does not accept.

## Closing out a piece of work
Answer four questions at the end of a task, a goal, or a session: what we set
out to do, what we did, what is left, and what decisions the operator owes.
Derive the factual half rather than recalling it:

    python scripts/run_session_summary.py --scope task --out "" --markdown-out ""

Feed your own claims back through the same command so they get checked. An
empty `--remaining ""` claims nothing is left, and the verdict returns
`SUMMARY_DISAGREES` when the tree still holds uncommitted or unpushed work.
Fix the claim, not the check. Scopes are `task` (head commit plus working
tree), `goal` (branch against its base), and `session` (goal plus receipts).

`--validation-ledger <path>` folds the output checks recorded during the run
into the third answer. Every entry short of a clean release is work that is
left, worst first, and a held entry raises a decision as well. The ledger
carries which fields were short, never the value an answer failed against.

`--strict` puts the result on the exit code: `1` a stated answer contradicts
the tree, `3` work is left, `0` nothing outstanding. Unfinished and wrong are
separate facts, and a script that merged them would report a run with held
output as clean.

## Hygiene
Never commit secrets, `.env` files, tokens, or private material to this public
repository. Verify before every commit. Branch before committing to a default
branch.
