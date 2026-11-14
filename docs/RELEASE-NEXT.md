# Next release notes

Retired on 2026-11-14. This page was last edited on 2026-09-23, when it
collected changes merged after 1.0.3. It is kept as written, because other
pages and tests cite it, and it is no longer updated. Changes that are merged
and not yet released are in `CHANGELOG.md` under "Unreleased". Changes that
affect an upgrade to 2.0 are in [MIGRATING-2.0.md](MIGRATING-2.0.md).

The notes below are the 2026-09-23 text.

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
- Hook receipts record the kind of a limit error found in the output and a
  token from a fixed vocabulary that names the pattern it matched, never the
  output's own words (`limit_signal`, `limit_match`). A hook can opt out of the output
  check at registration with `scan_output: false`.
- Every Rowan `agent.run` carries a run budget, and so does every
  `workflow.run`, `/api/workflow` and `plan.run` run, over all its stages. A
  stage the budget stops is recorded as `STOPPED` in the workflow receipt. See
  `docs/RUN-BUDGET.md`.
