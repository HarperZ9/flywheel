# Next release notes

These notes collect changes merged since 1.0.3 for the next release.

## Behaviour changes

- Schedules stop themselves. A schedule now stops firing after two failed fires
  in a row under one definition. A failed fire is any hook failure, blocking or
  not: a nonzero exit, a timeout, a runner error, or an exit 0 whose output ends
  on a rate limit, quota, billing, sign-in or service-overloaded error. Two
  failures inside one replayed backlog are enough, and fire history recorded
  before the upgrade counts. Owed occurrences are held until the owner re-arms
  the schedule with the Re-arm action in the Schedule view or
  `POST /api/schedule/rearm`. Earlier releases fired every owed occurrence
  whatever the hooks returned. See `docs/RUN-BUDGET.md`.
- Hook receipts record the kind and the matched words of a limit error found in
  the output (`limit_signal`, `limit_match`). A hook can opt out of the output
  check at registration with `scan_output: false`.
- Every Rowan `agent.run` carries a run budget, and so does every
  `workflow.run`, `/api/workflow` and `plan.run` run, over all its stages. A
  stage the budget stops is recorded as `STOPPED` in the workflow receipt. See
  `docs/RUN-BUDGET.md`.
