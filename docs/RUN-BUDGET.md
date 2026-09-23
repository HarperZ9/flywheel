# Run budget and the false-success check

Every Rowan `agent.run` carries a budget, and so does every staged run
through `workflow.run`, the `/api/workflow` route or `plan.run`. When a run
reaches a limit, the engine stops it at the next step boundary, records which
limit stopped it, and the desktop card shows the stop. A rate limit, quota, billing, sign-in or
service-overloaded (HTTP 503 or 529) error that the provider or the CLI reports
in its own fields counts toward a second breaker, and two in a row stop the
run. Tool output and the model's answer are never read for one. Scheduled jobs
read their hooks' output and stop themselves after repeated failed fires.

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
  cannot be refused beforehand.
- Claude CLI sessions report tokens twice. Each assistant event carries its
  message's `usage` (`input_tokens`, `output_tokens`,
  `cache_creation_input_tokens`, `cache_read_input_tokens`), and the final
  result event carries the same fields for the whole session, with the spend
  in `total_cost_usd`. One message can arrive as several events with the same
  message id, so the engine counts each message's tokens once, by id, as they
  stream. The result event then adds only the tokens the messages did not
  already report, so nothing is counted twice. A token limit crossed by a
  streamed message stops the session at its next tool call or model turn.
  Spend arrives only in the result event, so the spend limit marks a session
  stopped after the fact and cannot interrupt it. The result event is read on
  an errored session too, and a limit its numbers crossed is named in the
  record as the stop, while the session's own error stays the run's failure
  reason. A session stopped before that event keeps the tokens its messages
  reported, and names each model call with no reported usage as a call that
  reported nothing. Claude CLI cache reads and cache writes count as tokens,
  at the same weight as other input, so a session that re-reads a cached
  prompt on each turn reaches the token limit sooner; raise
  `max_usage_tokens` for a long CLI session.
- Codex CLI sessions report tokens per turn and neither the model calls inside
  a turn nor a cost. A turn counts as one model call, and a `run_budget` that
  sets `max_model_calls` or `max_cost_micros` for `codex-cli` is refused with
  `AGENT_CLI_BUDGET_UNSUPPORTED`.
- Wall time stays with the aggregate deadline over the worker process tree.
  When the worker sees the deadline itself, it records the wall-time stop with
  its own counts. When the process tree is stopped in the middle of a step,
  the worker writes nothing, so the gateway writes the record as it closes the
  run (`recorded_by: gateway_deadline`): a wall-time stop, with the limits and
  with the model calls, tool actions, check runs, tokens and spend the trace
  records. What only the worker held, such as a Claude CLI message's streamed
  tokens, is not in the trace and is not counted, and a model call with no
  recorded usage is named as one that reported nothing. The card says the time
  limit was reached before a budget record was written only when the gateway
  could not write one.
- The run's check command is the harness's step, not the model's, so a run
  of it does not use a tool action. Each run is recorded in the budget record
  as `harness_checks` and in the trace as a tool call marked `gate: test`, and
  the card lists the count next to the tool actions. A test-repair loop can
  run the check more than once. With `max_tool_actions` set to 0 the run's
  check command still runs. The same command run by the model, as its own
  tool call, uses one tool action like any other.

A stopped run fails with `AGENT_RUN_BUDGET_EXHAUSTED`. A run whose provider
or CLI reported success next to a limit error fails with
`AGENT_FALSE_SUCCESS`, as described below. The final answer is model prose on
every path and is never read for a limit, so a summary of work on rate-limit
or sign-in code completes.

## Where limit errors are read

A provider or a CLI reports a limit error in its own fields. Those fields are
the only place the engine reads one:

- Text and provider-native tool loops: the provider response's HTTP status,
  and the `error.type`, `error.code` and `error.status` fields of its body,
  read by exact value. A 429, 402, 401, 503 or 529 status is a limit error,
  and so is an error type such as `rate_limit_error`, `insufficient_quota`,
  `billing_error`, `authentication_error` or `overloaded_error`.
- Claude CLI sessions: the `error` field of an API error event (`rate_limit`,
  `billing_error`, `authentication_failed`), the `api_error_status` of the
  result event, and a `rate_limit_event` whose status is `rejected`.
- Codex CLI sessions: the status, code and type fields of an `error` or
  `turn.failed` event, and then its message.
- Both CLIs: the CLI process's own stderr, read at the end of the session for
  an anchored limit phrase, and its exit code.

Tool results and the model's answer are never read for a limit error. They
are content the model produced or read. A step that prints a test fixture
holding `"status": 429`, or an answer that opens "HTTP 429 responses are now
retried", describes a limit and does not report one the run hit. The run's
own check command is not read either, because its exit code is its verdict.

Each limit error is recorded in the budget report with where it was reported
(`provider`, `cli_api_error`, `cli_result`, `cli_rate_limit_event`,
`cli_error_event` or `cli_stderr`), its kind, and a token from a fixed
vocabulary such as `rate_limit_error` or `status 429`, never the text around
it. Two in a row stop the run, because a loop that retries into a limit keeps
spending. A provider call or a CLI model turn that reports no limit starts the
count again, and one error a CLI restates in a second event counts once.

A limit error reported next to a success is a false success, and the run
fails with `AGENT_FALSE_SUCCESS`: a 2xx provider response whose body is a
limit error, a CLI result marked success after the session reported a limit
error, or a CLI that exits 0 with a limit error on its stderr. The card lists
each counted error with where it came from and its token.

For example, claude 2.1.251, run against an account with no credit, streamed
an assistant event with `"error": "billing_error"` and
`"is_api_error_message": true`, then a result event with `"is_error": true`,
`"subtype": "success"` and `"api_error_status": 400`, and exited 1. The engine
records the `billing_error` and fails the session as incomplete.

A CLI's stderr and a scheduled hook's output are read as text, by the phrase
reader in `harness/limit_signal.py`. It sorts what it finds into three tiers:

- structured: an HTTP status line such as `HTTP/2 429`, or a JSON status,
  code, type or reason field such as `"status": 429` or
  `"type": "billing_error"`;
- terminal: the words a provider or CLI prints when it stops on a limit, such
  as "usage limit reached", "insufficient_quota" or "please run /login";
- mention: the same limits as prose, test names, commit subjects and retry
  logs use them, such as "rate limited" or "HTTP 429".

Only an anchored match is acted on: a structured match anywhere, a terminal
phrase on the text's last non-empty line, or a mention that opens that line
or follows an error prefix there ("Error: 429 Too Many Requests"). Short text
is read whole; long text is read at its head and tail. Each match carries its
kind and a token from the fixed vocabulary, never the words it was found in.

## Scheduled jobs

A schedule fires hook commands; it cannot start `agent.run`. Each hook receipt
names a limit error found in the hook's output with its kind (`limit_signal`)
and a token from a fixed vocabulary (`limit_match`), such as
`usage limit reached`, `invalid api key` or `status 429`. The token names the
pattern that matched and never carries the output's own words, so an account
or model name printed next to the error stays out of the receipt. A hook that
exited 0 is marked `false_success` only when the match
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

- Only the fields listed above are read. A limit a provider or a CLI reports
  in prose alone, outside those fields, is missed.
- The phrase reader used on a CLI's stderr and on hook output is an English
  phrase heuristic. It misses an error worded another way or written in
  another language (a German "Ratenlimit überschritten" is not seen), and an
  anchored match can still be a quote. A structured status code is read in any
  language.
- `workflow.run`, the `/api/workflow` route and `plan.run` run every stage
  under one budget for the whole workflow run, with the defaults above and a
  model-call limit that is the sum of the stages' step budgets. Each stage is
  settled when it returns, the same way `agent.run` is, so a crossed limit or
  a false success stops the workflow at that stage. The stage is recorded as
  `STOPPED` in the chained receipt with the stop code and the limit, and every
  stage summary carries the budget record as it stood. These routes take no
  `run_budget` override and have no aggregate deadline, so their wall time is
  recorded and not enforced.
- The Claude CLI stream shape above was checked against claude 2.1.251 on a
  local session that failed on a billing error: one assistant event and one
  result event, each with every token counter at 0. A successful multi-turn
  session was not observed. If the CLI reports a message's usage before the
  message is complete, the result event's total still adds the difference,
  but a session stopped before that event can undercount its last message.
- Usage a provider does not report is not counted. The record says how many
  calls reported nothing instead of estimating them. Most API providers report
  tokens but not cost, so the spend limit applies only where cost is reported.
- The breaker bounds one run. It does not cap spend across runs or across
  schedules.
- The approval sheet does not yet list the run budget separately. The card shows
  the limits before the run and the receipt records the resolved limits.
- The budget record is not a provider invoice.
