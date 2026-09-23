# Take a Rowan run elsewhere

A finished Rowan run exports as a Markdown brief that any other agent can read,
so the task continues there without being explained again. On the Rowan card,
**Copy handoff brief** puts it on the clipboard. The engine serves it to the
run's owner at `GET /api/operations/{operation_ref}/handoff`.

## What the brief holds

- **Goal**: the task as it was given.
- **Where it ended**: the run state and failure reason, the completion split
  (verified, claimed, failed) and whether the run budget stopped it.
- **Deliverables**: each file the run wrote and the final answer, with its
  mark and the check behind it (see `docs/VERIFIED-COMPLETION.md`).
- **Commands run**: up to 20, then a count of the rest.
- **Steps the model stated**: the model's own words per step, labelled as
  unchecked.
- **Open items**: work that is claimed and unverified, checks that failed, an
  unfinished run, a success claim with no check behind it, and steps that
  exited 0 while reporting a limit error.
- **Final answer**: quoted, and labelled as the model's words.
- **Receipts**: the operation, Journey and private trace references, the trace
  head hash, the ledger checkpoint and the run verdict.

The response also carries the trace reference, record count and head hash the
brief was rendered from. The engine refuses the brief when the trace no longer
matches the run's recorded result.

## Limits

- The brief is a plain export of one run. Nothing is re-run or re-checked when
  it is exported; the marks are the ones recorded at the end of the run.
- File contents are not included. The next agent needs the workspace to
  continue from the files themselves.
- The format is plain Markdown for any agent. Rendering context for a
  particular provider is not part of this export.
- Only the run's owner can read it, through the same authorization as the
  private trace.
