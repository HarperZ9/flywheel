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
| The final answer | `test_command` | The run's check command ran after the model said it was done, and passed on a trajectory that did not touch the check | The check failed, or passed on a trajectory that edited it |
| The final answer | `acceptance_criteria` | Every criterion passed | A criterion is still failing |
| The final answer | `run_state` | Never | The run stopped before it finished, for example on its budget |

A write whose tool reported success with no recorded hash is claimed. With no
check command, the final answer is claimed. Set a check command in the Rowan
card to change that; the engine runs it through the exec gate, so it needs exec
allowed. A check command that exits 0 while its output reports a rate limit,
quota, billing or sign-in error counts as a failed check (see
`docs/RUN-BUDGET.md`).

The card also flags an answer that says it succeeded when no check backs it.

## Native CLI sessions

The CLI runs its own tools, so the engine takes no hash at write time. A full
`Write` reports its content, and the file is rechecked against that. An `Edit`
reports only a fragment, so the file it touched stays claimed. The engine runs
no check command in a CLI session, so its final answer stays claimed.

## Where the record lives

The worker writes the full report, with paths, into the private trace next to
the result or the failure, and computes it while the workspace is still pinned,
so a run stopped by its budget still has its written files rechecked. The
terminal projection's `run_outcome.completion` block carries only the verdict,
the counts, and each item's kind, mark, check and a fixed detail word.

The gateway rechecks the report against the trace before it projects it, and
again on every read and in offline verification. It shows the report as
`unverifiable`, with the reason, when:

- a file the ledger says was written is missing from the report;
- a file's expected hash is not the one the ledger recorded;
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
- Effects outside files the run wrote with its own tools, such as a command
  that writes a file, are not deliverables in this report.
