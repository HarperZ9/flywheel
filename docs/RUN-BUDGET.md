# Run budget and the false-success check

Every Rowan `agent.run` carries a budget. When a run reaches a limit, the
engine stops it at the next step boundary, records which limit stopped it, and
the desktop card shows the stop. A step that exits 0 while its output reports a
rate limit, quota, billing or sign-in error is recorded as failed. Scheduled
jobs get the same output check and stop themselves after repeated failed fires.

## Limits

The owner sets overrides per run in the card's run budget row, or in the
operation's optional `run_budget` object. Unset limits take the default.

| Limit | Operation field | Default | Accepted range |
| --- | --- | --- | --- |
| Model calls | `run_budget.max_model_calls` | `max_steps` | 1 to 12 |
| Tool actions | `run_budget.max_tool_actions` | 24 | 0 to 200 |
| Provider-reported tokens, whole run | `run_budget.max_usage_tokens` | 200,000 | 1,000 to 10,000,000 |
| Provider-reported spend, whole run | `run_budget.max_cost_micros` | 2,000,000 (2.00 USD) | 10,000 to 1,000,000,000 |
| Wall time | `timeout_s` (existing) | 300 s | 1 to 1800 s |
| Limit errors in a row | fixed | 2 | not configurable |

`run_budget` is part of the approved operation, so the grant covers the exact
limits. An override that names an unknown limit, a boolean, or a value out of
range is refused as `INVALID_REQUEST`.

## How each path enforces it

- Text and provider-native tool loops: a model call or tool action past its
  limit is refused before it starts. Tokens and spend are known only after a
  call returns, so crossing either limit stops the next step; when the crossing
  call was the last one, the run still ends as stopped.
- Native CLI sessions: the CLI runs its own tools, so each call is counted as it
  streams past and the session is stopped at the first call over the limit. It
  cannot be refused beforehand. The CLI reports spend once, at the end, so a
  spend limit marks a CLI session stopped after the fact and cannot interrupt
  it.
- Wall time stays with the existing aggregate deadline over the worker process
  tree. The budget records it.

A stopped run fails with `AGENT_RUN_BUDGET_EXHAUSTED`. A run whose final answer
is itself a limit error fails with `AGENT_FALSE_SUCCESS`.

## The false-success check

A step's output is read for a limit error when the step is an action: a command
run, an MCP call, or a CLI tool call other than file reads, listings and edits.
File content is not read this way, so a file that mentions a rate limit does
not fail a step. Short output is read whole; long output is read at its head and
tail, where a CLI prints the error it stopped on.

A step that exited 0 with a limit error is recorded as failed, and the model
sees a one-line note saying so. Two limit errors in a row stop the run, because
a loop that retries into a limit keeps spending.

## Scheduled jobs

A schedule fires hook commands; it cannot start `agent.run`. Each hook receipt
now names a limit error found in the hook's output, and a hook that exited 0
with one is marked `false_success` and counts as failed. After two failed fires
in a row under one schedule definition, the tick stops firing that schedule and
says so, including in the middle of a replayed backlog. Only redefining the
schedule re-arms it; the passage of time leaves it stopped.

## What the projection carries

The terminal projection gains a content-free `run_outcome` block with schema
`flywheel.gateway-run-outcome/v1`. Its `budget` half comes from the budget
record in the private trace; its `completion` half is described in
`docs/VERIFIED-COMPLETION.md`. The gateway derives the block next to
`effect_evidence` and recomputes it on every read and in offline verification. A submitted block that differs is refused. A
record that does not add up is shown as `unverifiable` with a reason, for
example a stop on a limit the recorded numbers never reached, or a report that
counts fewer tool actions than the trace shows.

## Limits of this feature

- The limit-error check is a phrase heuristic. It misses an error worded another
  way, and it can flag a short output that quotes one of its phrases.
- Usage a provider does not report is not counted. The record says how many
  calls reported nothing instead of estimating them. Most API providers report
  tokens but not cost, so the spend limit applies only where cost is reported.
- The breaker bounds one run. It does not cap spend across runs or across
  schedules.
- The approval sheet does not yet list the run budget separately. The card shows
  the limits before the run and the receipt records the resolved limits.
- The budget record is not a provider invoice.
