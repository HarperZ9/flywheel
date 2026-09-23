# Verified and claimed completion

When a Rowan run ends, the card leads with what a check confirmed. Each
deliverable is marked:

- **verified**: a named check ran and passed;
- **claimed**: the model or its tool said so, and nothing checked it;
- **failed**: a check ran and did not pass, or the run did not complete.

Rowan says "Done" only when every deliverable is verified. Otherwise the card
says how much of the work rests on the model's word, or which checks failed,
with a line per deliverable naming the check behind its mark.

## The checks

| Deliverable | Check | Verified when | Failed when |
| --- | --- | --- | --- |
| A file the run wrote | `file_hash_recheck` | The file on disk at the end of the run has the hash the engine recorded right after the write | The file is missing, or changed after it was written |
| A file a command changed | none | Never: it is claimed, because nothing recorded what it should hold | Never |
| The final answer | `test_command` | The run's check command ran after the model said it was done, and passed on a trajectory that did not touch the check | The check failed, passed on a trajectory that changed what grades it, or never ran because the steps ran out before the model answered |
| The final answer | `run_state` | Never | The run stopped before it finished, for example on its budget |

The engine's record format also has an `acceptance_criteria` check for the
final answer. `agent.run` takes no criteria, so no Rowan run is verified or
failed that way today.

A write whose tool reported success with no recorded hash is claimed. With no
check command, the final answer is claimed. Set a check command in the Rowan
card to change that; the engine runs it through the exec gate, so it needs exec
allowed. Each run of the check uses one tool action from the run budget, and a
test-repair loop can run it more than once (see `docs/RUN-BUDGET.md`). The
check's exit code is its verdict: its output is not read for limit errors, so
a passing test log that names a rate-limit test case is still a pass.

The card also flags an answer that says it succeeded when no check backs it.

## What "did not touch the check" covers

These files grade the work, so a change to any of them during the run makes a
passing check untrusted:

- test files, at any depth: `test_*.py`, `*_test.py`, `conftest.py`, and
  anything under a `tests/` directory;
- the test runner's configuration: `pytest.ini` and `tox.ini` whole, and the
  `[tool.pytest...]` sections of `pyproject.toml` and the `[tool:pytest]`
  section of `setup.cfg`. A change elsewhere in those two files, such as a
  version bump, does not count.

The engine re-hashes these files on disk before each run of the check and
compares them with the start of the run, so a change counts whatever made it:
a write tool, a patch, or a shell command such as `sed` or `python -c`. A file
the check itself rewrote, such as a snapshot, is taken as the check's own
output and does not count against the next run of it.

Every file a command changed outside the engine's hashed write tools is also
listed as a deliverable, claimed (`changed_by_command`), so work done through
the shell never reads as verified. Files the check command itself changed are
left out of that list.

## Native CLI sessions

The CLI runs its own tools, so the engine takes no hash at write time. A full
`Write` reports its content, and the file is rechecked against that. An `Edit`
reports only a fragment, so the file it touched stays claimed. The last call on
a file decides: a `Write` followed by an `Edit` leaves the file claimed. Paths
are recorded relative to the workspace, and a write outside it is listed as
claimed without its host path. The engine runs no check command in a CLI
session, so its final answer stays claimed. A file a CLI `Bash` call changed is
not listed.

## Where the record lives

The worker writes the full report, with paths, into the private trace next to
the result or the failure, and computes it while the workspace is still pinned,
so a run stopped by its budget still has its written files rechecked. The
terminal projection's `run_outcome.completion` block carries only the verdict,
the counts, and each item's kind, mark, check and a fixed detail word.

The gateway rechecks the report against the trace before it projects it, and
again on every read and in offline verification. It shows the report as
`unverifiable`, with the reason, when:

- a file the ledger, or a CLI session's recorded `Write` and `Edit` calls, says
  was written is missing from the report;
- a file the end-of-run workspace diff found changed is missing from the
  report;
- a file's expected hash is not the one the ledger or the CLI call recorded;
- a mark does not follow from the recorded hashes;
- the answer is marked verified by the check command with no passing check run
  in the trace;
- the answer is marked verified on a failed run;
- the counts or the verdict do not match the items.

## Limits

- A file that matches its recorded hash can still be wrong. The recheck proves
  it was written as recorded and left that way, not that it is correct.
- A passing check command proves what the command checks and no more.
- The report lists at most 64 deliverables. When more exist, the counts cover
  all of them and the coverage recheck is skipped.
- A file a command changed is listed as claimed and never checked. The
  workspace diff reads at most 2,000 files and skips version control, cache
  and build directories, so a change past that limit or in those directories
  is not listed.
- The protected set is fixed. A check that reads some other file, such as a
  `package.json` script or a `Makefile`, is not watched.
