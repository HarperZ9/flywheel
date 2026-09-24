# Committed pytest oracle reports removed (2026-09-23)

Found while fixing the stale-report oracle bug in PR #288. This record covers
the follow-up on branch `chore/untrack-oracle-junit`.

## What was tracked

At commit 02a33d2dbf (main after #288), git tracked 1149 files named
`_oracle_junit.xml`, each one a distinct blob:

| Where | Reports |
| :-- | --: |
| `artifacts/uplift/work_*/<task>/` (11 runs of the hard uplift bench) | 1110 |
| `artifacts/agent_recovery_benchmark/<run>/loop/w/` and `spin/fw_*/` | 30 |
| `.flywheel-run/m7-tasks/<task>/workdir/` | 8 |
| `tasks/example_pass/workdir/` | 1 |

Every report named the build machine in its `hostname` attribute. 63 also held
absolute local paths, a user profile path among them, in the tracebacks of
failed imports and assertions: 62 under `artifacts/uplift/` and the one in
`tasks/example_pass/workdir/`. No tracked file named `_oracle_junit_<nonce>.xml`
existed, and no other tracked XML file had a JUnit root element.

## How references were checked

A script outside the repository searched every other tracked file for each
report by:

- its relative path, and its parent directory plus file name, spelled with
  forward slashes, backslashes, and JSON-escaped backslashes;
- the SHA-256 of its blob, the SHA-256 of its checked-out bytes, its git blob
  id, and the tree id of every directory above it, in full or as any hex token
  of 7 or more characters that is a prefix of one;
- the outcome digest the pytest oracle computes from it,
  `_digest(_pytest_canonical(report), rc)` for rc 0 to 5.

What it found:

- Byte references (SHA-256, blob id, tree id): none, for all 1149.
- Path references: the six `loop/w/` reports. Twelve loop receipts
  (`loop/cache/*.json`, `loop/env/*.json`) quote pytest's stdout, which
  includes the line `generated xml file: ...\loop\w\_oracle_junit.xml`. That
  path is where pytest wrote on the build machine. The receipt does not hash
  the file. The run README of `20260708_230923` also cited its four spin
  reports for their `tests="0"`.
- Outcome digest matches: 24 reports. The 8 m7 workdir reports record the
  outcomes that the 8 receipts in `.tmp-flywheel-cache/` hash. Six `loop/w/`
  reports and ten `spin/fw_pass_*` reports record the outcomes behind
  `6ff02b6122044a86`, the output hash of the 12 loop receipts. A match says a
  report and a receipt saw the same outcomes. It does not make the report an
  input to the receipt.

## Decision: remove all 1149, keep none

- No receipt's hash rule reads a committed report. The output hash covers the
  sorted test outcomes and the exit code, and a witness re-derives it by
  running the recorded `oracle_cmd` again. Since #288 the oracle and the
  witness read only the report their own run wrote, and delete it after.
- Checked on all 20 receipts whose output hash matched a removed report: the
  8 in `.tmp-flywheel-cache/` and the 12 loop receipts, one in `loop/cache/`
  and one in `loop/env/` for each of 6 runs. In every run the `loop/env`
  receipt matches the `loop/cache` receipt field for field. For each receipt,
  the tracked workdir was copied with every report left out, the receipt's
  candidate written, and the receipt's `oracle_cmd` run with the report token
  bound to a fresh name. 20 of 20 reproduced the recorded hash. The control
  wrote an empty candidate into the same 20 copies, and 0 of 20 reproduced
  it. Run on Windows, Python 3.12.10, pytest 8.4.2. The loop receipts quote
  pytest 9.0.3 and Python 3.12.10 as the versions they were recorded with.
- A first pass re-ran only the 14 distinct receipts, the 8 cache receipts and
  the 6 in `loop/cache/`, and got 14 of 14. The message of commit b0a57fd2
  reports that pass as if the 14 were every receipt that matched. The full
  set is the 20 above.
- The 9 task-workdir copies were a live hazard before #288. On a fresh clone,
  a candidate that exits before pytest writes read the committed report and
  passed. They go regardless of references.
- Scrubbing the host from the ten referenced reports would leave every digest
  unchanged, so the hash rule allows it. It would also keep a report sitting in
  an oracle workdir, which is the shape #288 removed, and no check needs one.
- The run README of `20260708_230923` now names the commit and the blob ids
  that hold its four spin reports.
- The gate grandfathers nothing.

## What stops a new one

- `.gitignore` ignores `_oracle_junit.xml` and `_oracle_junit_*.xml` at any
  depth.
- `python scripts/check_tracked_junit.py`, pinned by
  `tests/test_check_tracked_junit.py` and run by the `junit_reports` CI job,
  exits 1 on any tracked JUnit report with a non-empty `hostname` attribute or
  path-shaped text. It finds a report by the oracle's file name, or by a
  `<testsuites>` or `<testsuite>` root element in any tracked file, whatever
  its name or extension. It skips an XML prolog before the root, and it reads
  UTF-8, UTF-16, and UTF-32 with a byte order mark. So `git add -f` fails, and
  so does a report under another name. The script's docstring lists the
  shapes it does not catch.
- The path rule errs toward failing. A path-shaped literal from a test's own
  source, such as `'/tmp/cache'`, fails too, because the gate cannot tell it
  from a path on the build machine.
- Run on commit 02a33d2dbf, the gate as committed here finds the same 1149
  reports, all 1149 naming a host and 63 holding absolute paths.

## Recheck

- `git ls-tree -r --name-only 02a33d2dbf | grep -c _oracle_junit` prints 1149.
- `git show 02a33d2dbf:<path>` prints any removed report.
- `python scripts/check_tracked_junit.py` exits 0 and counts 0 reports.
- With a detached worktree of 02a33d2dbf at `<dir>`, this command, run from
  this checkout, exits 1 and ends with
  `1149 of 1149 tracked JUnit reports name a host or an absolute path`:
  `python -c "import sys; sys.path.insert(0, 'scripts'); import check_tracked_junit as g; sys.exit(g.main(sys.argv[1]))" <dir>`.

## Does not prove

- That the tree names no machine. The 12 loop receipts under
  `artifacts/agent_recovery_benchmark/*/loop/cache/` and `loop/env/` quote
  pytest's stdout, and its `rootdir` and `generated xml file` lines hold
  absolute local paths. They are receipts, the gate does not read them, and
  this change leaves them as they are. The 8 receipts in
  `.tmp-flywheel-cache/` hold no absolute path: their stdout excerpt is only
  pytest's progress line.
- That the reports are gone from the public record. Git history keeps every
  removed blob.
- That the re-derivation holds on another host or pytest version. It ran on
  one Windows host with Python 3.12.10 and pytest 8.4.2.
