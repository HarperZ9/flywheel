# Public Audit: CrewAI Latest-Run Replay

## Conclusion

At CrewAI `b3aaaab023a53a08db4d36c9430b3463f1efcc7d`, synchronous non-streaming `Crew.kickoff_for_each` does not conform to the pinned documentation's most-recent-run replay promise.

Unmodified Python 3.12 evidence:

- regression: exit 1, 1 failed, stored output count was 0 instead of 1;
- ordinary-`kickoff` control: exit 0, 1 passed;
- combined: exit 1, 1 failed and 1 passed.

Local one-line candidate evidence:

- focused regression/control/combined: exit 0, 1/1, 1/1, and 2/2;
- selected existing `kickoff_for_each`: exit 0, 8/8;
- selected existing replay: exit 0, 9/9;
- Ruff, formatting, diff, and patch checks: exit 0.

## Contract

Both of these pinned files state that only the latest kickoff is supported and that, with `kickoff_for_each`, replay is from the most recent crew run:

- `docs/edge/en/learn/replay-tasks-from-latest-crew-kickoff.mdx:10-14`
- `docs/v1.15.6/en/learn/replay-tasks-from-latest-crew-kickoff.mdx:10-14`

Their identical SHA-256 digest is `5cc02ff62d16dfc79bbcbe0b37497f76a665c507cb548ccc96eb8049c2ededa0`.

## Root cause

Each copied kickoff resets the shared latest-output SQLite store before it executes. Runs are sequential, so the final copy leaves the newest records. Unmodified `Crew.kickoff_for_each` then resets the parent handler after the loop and deletes those valid records. `Crew.replay` therefore has nothing to load.

The candidate removes only that terminal reset:

```diff
-        self._task_output_handler.reset()
         return results
```

## Test validity

The test uses real Crew construction, copying, interpolation, persistence, stored-input recovery, and replay. Only `Task.execute_sync` is replaced with deterministic `TaskOutput` generation. The regression verifies two batch outputs, final stored inputs, a third replay execution, its interpolated description, its returned output, and a truthy persisted replay marker.

Exact loopback-only host patterns are allowed for Windows `socket.socketpair`; other network access remains subject to the repository guard. The claim is limited to exercised pytest paths.

## Provenance boundary

The RED/control files record the run chronology before the production deletion. They do not embed an adjacent source digest or status, so they are evidence, not cryptographically self-attesting execution receipts. The clean baseline, retained logs, and final one-line production diff support the chronology.

The test later gained stronger post-replay assertions. The original failing storage-count assertion remains unchanged and occurs before the added assertions.

## Limitations

- Synchronous, non-streaming path only.
- Async and streaming paths not runtime-audited.
- Full repository suite not run.
- Empty-input persistence semantics need maintainer judgment.
- Private storage state is inspected diagnostically alongside public replay behavior.
- No upstream duplicate search performed.

## Recommendation

A narrowly scoped maintainer bug report is warranted after duplicate search. Include the pinned contract, Python 3.12 environment, RED/control/GREEN evidence, candidate patch, and scope limits. CrewAI Tools 1.15.6 was installed by the locked workspace but was not involved.
