# Null floor for the cross-harness oracles, 2026-09-03

## What was measured

Every configured oracle checker, driven with three submissions that did not do
the task:

- `empty` writes an empty report.
- `shape` keeps the report's keys and empties every value a provider could not
  derive from its own inputs.
- `echo` copies the fixture's own fields back and empties the rest.

Three fields stay filled under every strategy, because a provider can produce
them from its inputs alone: `task_id`, `input_sha256s`, `receipt_input_sha256s`.
Hollowing those would test the shared preamble instead of the checker, and all
three strategies would collapse into the same trivial rejection.

Run it:

```bash
python scripts/run_null_floor.py --fail-on-breach
```

## Result

`NULL_FLOOR_BREACHED`. 15 candidates, 5 checkers, 3 strategies, 5 checkers
reached by at least one candidate.

| checker | empty | shape | echo |
| --- | --- | --- | --- |
| index_fallback_integrity/v1 | malformed (preamble) | fail | fail |
| shared_task_artifact/v1 | malformed (preamble) | malformed | malformed |
| paired_friction/v1 | malformed (preamble) | fail | fail |
| documentation_maintenance/v1 | malformed (preamble) | fail | **pass** |
| documentation_maintenance/v2 | malformed (preamble) | fail | fail |

One breach. `documentation_maintenance/v1` scores a submission that hands its
own fixture back as a correct answer. Every comparison the checker makes is
report-against-fixture: surface names, paths, code references. A provider that
read only its input satisfies all of them without opening a single file. The
report's `synchronized` and `gate_passed` fields are read and never asserted on,
so emptying them costs nothing.

That checker was used in the head-to-head. Any `documentation_maintenance/v1`
pass in a scored run is consistent with transcription and does not distinguish
work from restatement.

## The fix

`documentation_maintenance/v2` in `harness/cross_harness_oracles_v2.py`. It
keeps every v1 comparison and adds two facts per surface that the fixture does
not carry: the sha256 of the documentation file and the sha256 of each code
reference, read from the workspace. The echo candidate now fails with
`surface_digest_missing`.

v1 is left in place rather than tightened. A run already scored under v1 stays
comparable to itself, and the version number carries the change. Migrating the
task set to v2 is a separate decision, because it rescores prior runs.

The digests also catch drift v1 was blind to: editing a documentation surface
after the report is written now returns `surface_digest_mismatch`, where v1
reads the file and ignores its content.

## Two defects found in the measurement itself

**A vacuous floor.** The first run rejected all 12 candidates with the same code
and looked like a clean hold. It was not. `Path.write_text` translates a newline
on Windows, the oracle reads artifact bytes and decodes them, and the envelope
built from in-memory strings therefore disagreed with the files on disk. Every
candidate died at the shared preamble for a reason that had nothing to do with
any checker. The envelope is now built from `read_bytes().decode("utf-8")`, and
the report carries `checkers_reached` and `checkers_never_reached` so a floor
that holds because nothing was measured says so.

**An ambiguous stage.** `json_invalid` is emitted both by the preamble when a
report will not parse and by the top-level handler when a checker raises.
Reading codes alone put `shared_task_artifact/v1` in `checkers_never_reached`
when its checker had in fact run. `rejected_at` now reads `evidence["reason"]`,
and only `raw_output_invalid`, `response_envelope_invalid` and
`attempt_path_invalid` come from before a checker runs.

## What this does not prove

- A held floor does not show a checker rewards a correct answer. It shows the
  checker rejects three specific ways of not answering. The control case, which
  asserts the good submission still passes, is what covers the other direction.
- The strategies are exhaustive over nothing. A fourth kind of cheap candidate
  may still pass.
- This measures the checkers, not the providers. A task no provider can execute
  still holds its floor.
- v2 requires digests. It does not check that the documentation is correct, only
  that the candidate opened the files it reported on and that they have not
  changed since.
