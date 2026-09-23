# Run budget and the false-success check

Every Rowan `agent.run` carries a budget. When a run reaches a limit, the
engine stops it at the next step boundary, records which limit stopped it, and
the desktop card shows the stop. A step that exits 0 while its output ends on a
rate limit, quota, billing, sign-in or service-overloaded (HTTP 503 or 529)
error counts toward a second breaker, and two such steps in a row stop the run.
Scheduled jobs get the same output check and stop themselves after repeated
failed fires.

## Limits

The owner sets overrides per run in the card's run budget row, or in the
operation's optional `run_budget` object. Unset limits take the default. The
card applies each field as it is typed, with no need to press Enter, and shows
the default in an empty field. A value outside its range is named under the
field, and the card refuses to start the run until it is fixed, so a run never
goes out under limits the field does not show.

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
  cannot be refused beforehand. The CLI reports tokens and spend once, for the
  whole session, in its final result event, so both the token limit and the
  spend limit mark a CLI session stopped after the fact and cannot interrupt
  it. The result event is read on an errored session too. A session stopped
  before that event names every model call it saw as a call that reported
  nothing. Claude CLI cache reads and cache writes count as tokens, at the
  same weight as other input, so a session that re-reads a cached prompt on
  each turn reaches the token limit sooner; raise `max_usage_tokens` for a
  long CLI session.
- Codex CLI sessions report tokens per turn and neither the model calls inside
  a turn nor a cost. A turn counts as one model call, and a `run_budget` that
  sets `max_model_calls` or `max_cost_micros` for `codex-cli` is refused with
  `AGENT_CLI_BUDGET_UNSUPPORTED`.
- Wall time stays with the aggregate deadline over the worker process tree. The
  budget records a wall-time stop only when the worker sees the deadline
  itself. When the process tree is stopped in the middle of a step, no budget
  record is written, and the card says the time limit was reached before one
  was.
- The run's check command runs through the same executor, so each run of it
  uses one tool action. A test-repair loop can run it more than once. With
  `max_tool_actions` set to 0 a run that has a check command stops at the
  check.

A stopped run fails with `AGENT_RUN_BUDGET_EXHAUSTED`. A native CLI session
that ends marked success, with a short result text that opens with a limit
error, fails with `AGENT_FALSE_SUCCESS`. On the text and provider-native
paths the final answer is model prose and is not read this way: a provider
limit there already fails the call as a non-2xx response, and a summary of
work on rate-limit or sign-in code would read as a false failure.

## The false-success check

A step's output is read for a limit error when the step is an action that
exited 0: a command run, an MCP call, or a CLI tool call other than file reads,
listings and edits. File content is not read this way. The run's own check
command is not read either, because its exit code is already the verdict and a
passing test log can name a rate-limit test case. A nonzero exit is a failure
the model already sees, so it is not read. Short output is read whole; long
output is read at its head and tail.

The check sorts what it finds into three tiers:

- structured: an HTTP status line such as `HTTP/2 429`, or a JSON status,
  code, type or reason field such as `"status": 429` or
  `"type": "billing_error"`;
- terminal: the words a provider or CLI prints when it stops on a limit, such
  as "usage limit reached", "insufficient_quota" or "please run /login";
- mention: the same limits as prose, test names, commit subjects and retry
  logs use them, such as "rate limited" or "HTTP 429".

Every match is recorded in the budget report as a suspected false success,
with the tool and the matched words, and the step result the model sees is
left as it was. A match counts toward the breaker only when it is anchored: a
structured match anywhere, a terminal phrase on the output's last non-empty
line, or a mention that opens that line or follows an error prefix there
("Error: 429 Too Many Requests"). Two counted steps in a row stop the run,
because a loop that retries into a limit keeps spending. Any other step in
between, a file write included, starts the count again. The card lists the
counted steps with their matched words, so the owner can tell a real limit
from a quote.

## Scheduled jobs

A schedule fires hook commands; it cannot start `agent.run`. Each hook receipt
names a limit error found in the hook's output with its kind and the matched
words (`limit_signal`, `limit_match`, at most 80 characters of the fixed
vocabulary). A hook that exited 0 is marked `false_success` only when the match
is anchored, as described above: a status line such as "0 requests were rate
limited" or "GET /v1/items -> status 429, retried" is recorded and does not
fail the hook.

A fire failed when any hook it ran failed, blocking or not:

- a nonzero exit;
- a timeout or a runner error;
- an exit 0 marked `false_success`.

After two failed fires in a row under one schedule definition, the tick stops
firing that schedule and says why, with the matched words. Two failures inside
one replayed backlog, fired seconds apart, are enough. Fire history recorded
before this check existed counts the same way. A stopped schedule's owed
occurrences are held, not due: the roster lists them under `plan.held`, counts
them under `pending.held` with `pending.due` at 0, and sets
`any_breaker_tripped`.

The passage of time leaves a stopped schedule stopped. To re-arm it, press
Re-arm on its row in the desktop Schedule view, or call
`POST /api/schedule/rearm` with `{"schedule_id": ...}`. A re-arm re-seals the
stored definition with a new `created_at` and changes nothing else, so the fire
history and the owed occurrences are kept. Redefining the schedule through
`POST /api/schedule/define` also re-arms it.

A hook whose normal output discusses limits, such as a rate-limit monitor, can
be registered with `scan_output: false`. Its exit code alone then decides
whether it failed. The choice is part of the sealed registration.

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

- The limit-error check is an English phrase heuristic. It misses an error
  worded another way or written in another language (a German
  "Ratenlimit überschritten" is not seen), and an anchored match can still be
  a quote. A structured status code is read in any language.
- The budget covers `agent.run` only. `workflow.run`, the `/api/workflow`
  route and `plan.run` drive the same router loop with no run budget and no
  false-success check; their stages are bounded by each stage's `max_steps`.
- Usage a provider does not report is not counted. The record says how many
  calls reported nothing instead of estimating them. Most API providers report
  tokens but not cost, so the spend limit applies only where cost is reported.
- The breaker bounds one run. It does not cap spend across runs or across
  schedules.
- The approval sheet does not yet list the run budget separately. The card shows
  the limits before the run and the receipt records the resolved limits.
- The budget record is not a provider invoice.
