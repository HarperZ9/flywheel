# Records written by Flywheel 1.x releases

One sealed record set from each 1.x minor, 1.0 to 1.9, written by that
release as published on PyPI. They back the promise in `docs/VERSIONING.md`
that every 2.x release reads and verifies every 1.x record.
`tests/test_compat_records_1x.py` verifies each set and runs the controls.
`python scripts/verify_compat_records.py --control` does the same from a
checkout or beside an installed wheel.

## What a record set is

| File | Written by | What it is |
|---|---|---|
| `gate_envelope.json` | `flywheel gate DIR` | The proof envelope the built-in gate seals: a rank-7 scheme for 2x2 matrix multiplication, checked by the exact oracle. |
| `gate_report.json` | `flywheel gate DIR` | The step report. It names the envelope by its content digest and its claim digest and records the re-witness result. |
| `receipt.json` | `make_receipt.py` with the release's `harness.receipt.Receipt` | A `flywheel.receipt/v4` receipt sealed over the same candidate. It carries the scope list under the 1.x name. |

The gate has no model in it and is deterministic, so the two gate files have
the same bytes in every release. The receipt differs per release: it records
the release that wrote it.

## Provenance

Produced on 2026-11-14 on Windows 11 with Python 3.12.10. Each release was
installed from its PyPI wheel into its own new environment, one at a time.
Every one of the eleven installed, ran the gate to `verdict=PASS
rewitness=MATCH`, and sealed its receipt. No release had to be skipped.

| Release | Wheel SHA-256 (from PyPI) | Receipt claim digest (first 12) |
|---|---|---|
| 1.0.0 | `b9cadf874456d474d197d1f1a8b1ba5edad0eea92a5c03559aaa855030126193` | `8e0c88096d69` |
| 1.0.4 | `8b3524b147937bff8bfd86efe522ee2468891297c75721683b7a401bb186f508` | `58d2393c3c60` |
| 1.1.2 | `a33ef8b119c64e96916f360bf3e5932b0752fb20e353521c49a7bebc11e6692d` | `65cd12619f32` |
| 1.2.1 | `e862af0bd5a1add80275148923c6092ee016c30930fd64027414a0972b340447` | `3ea107f1c027` |
| 1.3.4 | `1fdb65fef7a5fae82723e38a349c8d5fbf1bc251dfca9a5f39e82b89c9668ea6` | `2bee33676522` |
| 1.4.0 | `a9bae06f5cdf5f2dab4f12396fdf230dd5c8b73f21c9e42aa10e51ee7f53332e` | `2fdd1e322ba3` |
| 1.5.1 | `0d58571a26a2407e668e81c0055b51772dcf116414cbe5dc3511eec84fd8ad7d` | `1fb61260423f` |
| 1.6.0 | `7ff54574e39a886ef731096a3bf135a1fc3033c6547d28ec8396c94e30d8d129` | `f7b410f0ce5b` |
| 1.7.0 | `1e9da3d1cfdcce5c49899e7deb23cc57c18e8b8c055a453108342d99544f6905` | `f99ac7bfe22c` |
| 1.8.0 | `beae9906af0bd01329a147c66d095825aaf8272b9fa7d66f947ae7fa48d45893` | `ba92ae56aa4d` |
| 1.9.0 | `6514e581ce1e684ce157cd50c59e8c48543fa32a9a070bdf27226da8237d39d5` | `68344aca4e21` |

Each minor is represented by its last patch release. 1.0.0 is kept as well
because it is the oldest 1.x release a record can come from.

## The commands

Run once per release, with `V` set to the version and `FIX` to this folder:

```
python -m pip download --no-deps --only-binary :all: -d wheel "flywheel-verify==$V"
python -m venv venv
venv/Scripts/python -m pip install --no-deps wheel/*.whl
mkdir work && cd work
../venv/Scripts/flywheel gate record
../venv/Scripts/python -I "$FIX/make_receipt.py" record
```

On Linux and macOS the interpreter is `venv/bin/python` and the command is
`venv/bin/flywheel`. The three files in `work/record` were then copied to
`<release>/` here.

One change was made to the bytes. On Windows the gate writes its two files
with CRLF line ends; they are stored here with LF, as the repository stores
all text. No digest in a record covers the line-end form. `SHA256SUMS` lists
the SHA-256 of every file as stored.

## What the check covers

A set reads MATCH when every file parses, is in the form its writer
produces, re-derives its own digests, agrees with the other two files, equals
what the current gate seals on every field the old record states, and the
oracle re-run over the stored candidate reaches the stored result.

Controls, run on every change:

- One byte changed at every offset of every file, 51,084 changes in all. None
  may read MATCH.
- Each receipt given the scope list under both field names. Each must be
  refused.
- A reader that answers MATCH to everything is run through both controls and
  must be caught by both.

One limit the byte control found. `harness_version` is the one receipt field
that neither receipt digest covers, in schema v3, v4 and v5. A receipt alone
cannot show that this field was edited. Here it is bound two other ways: it
must equal the release folder it sits in, and the file must match
`SHA256SUMS`.

## Adding a release

Run the commands above for the new release, copy its three files into a new
folder, and add three lines to `SHA256SUMS` (the SHA-256 of each file with LF
line ends, two spaces, then `<release>/<file>`). Never edit a stored record.
