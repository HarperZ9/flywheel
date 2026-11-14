# Moving from Flywheel 1.x to 2.0

This page lists every change in 2.0 that can affect a script, a config file,
a stored record or a habit carried over from 1.x. Most people upgrade and
carry on. Sections are added here as later parts of 2.0 land.

2.0.0 shipped these changes without a deprecation release before it. The
[versioning page](VERSIONING.md) records that as a dated exception and says
which releases still get fixes.

## What you need to do

Nothing, if you use `flywheel code`, the desktop app or the gateway by hand.
Read the matching section if one of these is true:

1. **A script or program reads `does_not_prove` from Flywheel JSON.** Read
   `scope` in records written by 2.0, and keep reading the older name in
   records written by 1.x. See "Records: `does_not_prove` is now `scope`".
2. **Something matches an exact schema string**, such as
   `flywheel.receipt/v4`. Accept the new version too. The full list is on the
   [schema page](MIGRATING-2.0-SCHEMAS.md).
3. **An MCP client reads the output of Flywheel's receipt tools.** The output
   schema is `flywheel.receipt-operations/v2`.
4. **A client reads `usage` from the gateway or the agent response.** It now
   holds provider token counts or `null`. See "The `usage` field of a served
   response".
5. **You relied on commands in `flywheel code` being unable to write in the
   project.** They can now. Set `FLYWHEEL_WORKSPACE_WRITES=0` to keep the 1.x
   behaviour. See "Commands may write in the project folder".
6. **A proxy sits between Flywheel and a hosted provider.** It must pass
   server-sent events, `tools` lists and Anthropic `cache_control` marks, or
   you switch each off. See "The coding session on hosted models".
7. **A hook mount names `wrapper_scaffold_hook.py` or
   `wrapper_turn_receipt_hook.py`.** Mount the module. See "Removed: the two
   old hook scripts".
8. **Python code imports `harness`.** Some names changed. See "Python names".
9. **A custom certificate family stops on a budget, or you rely on the
   stated-limit audit detector.** See "Verdicts and audits".
10. **A client sends `POST /v1/messages` to the gateway.** The gateway now
    answers it and routes by the `model` field. See "The gateway".
11. **A client reads `usage` from the model server's `POST /chat/completions`.**
    It is `null` when the model reported no counts, where 1.x sent `{}`. See
    "Usage on every served endpoint".

You never need to convert a stored record. Every sealed, anchored or saved
1.x record verifies in 2.x with its original bytes.

After upgrading, run the checks under "How to check an upgrade".

## Records: `does_not_prove` is now `scope`

In 1.x a record carried `does_not_prove`: a list, or sometimes a string, of
limits, each written as a negative sentence or a `NOT_PROVES_*` code. In 2.0
a record carries `scope` in the same place, and each entry says what the
result covers.

The rules:

- A record written by 2.0 carries `scope`. It never carries both names.
- The type is unchanged. A list stays a list and a string stays a string.
- Every schema whose records changed moved up one version. A 2.0 writer emits
  only the new version.
- A 2.x reader accepts both versions and reads each with its own field name.
  Where a reader enforces a field contract, a record that carries the other
  version's name is refused.
- Each value was rewritten. A limit that applied when a condition failed
  became a coverage entry that is present when the condition holds. A
  script that tested for a `NOT_PROVES_*` code must test for the absence of
  the new code, or for the new code with the opposite meaning.

### What was renamed

| 1.x | 2.0 | Where it shows |
|---|---|---|
| field `does_not_prove` | field `scope` | Receipts, routed receipts, QA cards, witnesses, evidence packets, gateway and MCP outputs, bulletin, writing, trace and statistics records, reports |
| field `extra_does_not_prove` | field `extra_scope` | `flywheel.receipt/v5` |
| `NOT_PROVES_*` receipt codes | codes for the covered property, such as `PREDICATE_EXACT` | The receipt's list. All 15 pairs are on the [schema page](MIGRATING-2.0-SCHEMAS.md) |
| `NOT_PROVES_OPTIMALITY` | `BOUND_FROM_SUBMITTED_OBJECT` | Certificate and oracle results |
| failure code `schema_or_limits` | `schema_or_scope` | Signed job result verification |
| `flywheel.receipt/v4` | `flywheel.receipt/v5` | Receipts. v3 and v4 are still read |
| `flywheel.routed-receipt/v1` | `flywheel.routed-receipt/v2` | Routed receipts |
| `flywheel.oracle-qa-card/v2` | `flywheel.oracle-qa-card/v3` | QA cards |
| `flywheel.receipt-operations/v1` | `flywheel.receipt-operations/v2` | Output of the MCP receipt tools |
| printed heading for the list | `scope:` | Text, Markdown, LaTeX and HTML reports |

The [schema page](MIGRATING-2.0-SCHEMAS.md) lists every schema that moved,
158 rows in all, with the records that have no version id and the ones that
did not change. It is generated from the code and the migration checklist.

### How to read old and new records

In Python, use the shared reader. It accepts either name:

```python
from harness.scope import scope_list

entries = scope_list(record)   # a list of strings, whichever name the record uses
```

In another language, look for the older name first:

```
entries = record["does_not_prove"] if "does_not_prove" in record else record.get("scope")
```

The older name goes first because a few 1.x records also carry an unrelated
string label called `scope`.

### What does not change

- Every sealed, anchored, signed or saved 1.x record verifies with its
  original bytes. The repository keeps a record set written by each 1.x minor
  and verifies all of them on every change; see
  [Versions and compatibility](VERSIONING.md), "Records stay checkable".
- Records in superstack's receipt format keep `does_not_prove`. That format
  belongs to superstack, and Flywheel reads and writes it unchanged.
- The four verdicts (PASS, FAIL, UNDECIDED, UNVERIFIABLE) and the MATCH and
  DRIFT recheck results.

### Python names

The Python modules under `harness` are not in the list of things the
versioning page covers, so these are stated for convenience.

| 1.x | 2.0 |
|---|---|
| `OracleResult.does_not_prove` | `OracleResult.scope` |
| `Receipt.extra_does_not_prove` | `Receipt.extra_scope` |
| `Receipt.does_not_prove()` | `Receipt.scope()` |
| module constants named `DOES_NOT_PROVE` | `SCOPE` |
| module functions named `does_not_prove()` | `scope()`, or a local name where `scope` was taken |

## The coding session on hosted models

### Replies from hosted providers stream by default

In 1.x the interactive `flywheel code` session printed a reply from Anthropic,
OpenAI, an OpenAI-compatible host or Gemini when it was complete. In 2.0 the
text prints as the model writes it.

What stays the same:

- The ledger entry for a reply, its receipt id, the saved conversation and the
  token counts. A streamed turn and a plain turn record the same thing.
- `flywheel code -p`, `--output-format json`, `--output-format stream-json`
  and `--acp`. None of them uses the provider stream.
- Azure OpenAI, Amazon Bedrock, Google Vertex AI and the subscription CLIs.
  Their replies still print whole.

What changes:

- The request to the provider carries its stream switch (`stream: true`, or
  `streamGenerateContent` for Gemini). If you run a proxy or a gateway between
  Flywheel and the provider, it has to pass server-sent events through.
- A reply that is cut off part way no longer has a chance to arrive whole. If
  the connection drops after text has begun, the turn fails with the reason,
  nothing from it is recorded, and no tool call from it runs. Send the request
  again to retry. In 1.x the same network fault failed the turn before any
  text was shown.
- The note printed when a stream fails changed from
  `[stream interrupted; the reply follows]` to
  `[stream interrupted; the text above is not the reply]`. It is text for
  people and was never a stable output, but a script that matched it needs the
  new wording.

To keep the 1.x behaviour, set `FLYWHEEL_STREAM=0`. Streaming is also off in
`--plain` mode and with `FLYWHEEL_SCREEN_READER=1`.

How to check after upgrading: run `flywheel code`, ask a question that needs a
long answer, and watch the text arrive in pieces. Then run `/status` and
confirm the chain verifies.

### Tool calls use the provider's function calling by default

In 1.x every model asked for a tool by writing a `TOOL name {json}` line. In
2.0 the session declares its tools as JSON schemas to OpenAI
(`api.openai.com`), Anthropic (`api.anthropic.com`) and Gemini
(`generativelanguage.googleapis.com`) and reads their native tool calls.

What stays the same:

- Session, receipt and ledger formats. A native call is recorded as the TOOL
  line the text protocol would have carried, so a ledger written by 2.0 has
  the same entry kinds and the same content shapes as one written by 1.x.
- Permission modes, rules, hooks and prompts. The same executor decides and
  runs every call.
- Every other backend. Local models, subscription CLIs, Azure, Bedrock,
  Vertex, DeepSeek, OpenRouter and other OpenAI-compatible hosts keep the text
  protocol unless you opt in.

What changes:

- Requests to the three hosts above carry a `tools` list, and the part of the
  system prompt that explains how to call a tool is worded for function
  calling. A proxy that rewrites or rejects `tools` will see different
  traffic. The system prompt on the record, and the receipt computed over it,
  keep the 1.x wording.
- The harness-config ledger entry has a new field, `native_tools`, so the
  config hash of a 2.0 session differs from a 1.x session with the same
  settings. The hash already included the Flywheel version, so hashes never
  matched across releases.
- A native reply that carries a tool-result object is refused and the turn
  fails, because only the session produces tool results. 1.x had no native
  replies, so no 1.x session meets this.

To keep the 1.x behaviour, set `FLYWHEEL_NATIVE_TOOLS=0`. To use native calls
on another host that supports them, set `FLYWHEEL_NATIVE_TOOLS=1`.

### Anthropic requests are marked for prompt caching by default

In 1.x a coding session sent Anthropic the system prompt as plain text and no
cache marks. In 2.0 it sends the system prompt as one text block with a cache
mark and adds a second mark at the top level of the request.

What stays the same: the ledger, the receipts, and every request to a provider
other than Anthropic.

What changes:

- Billing on Anthropic. The provider bills a cache write above its normal
  input rate and a cache read far below it. A session with many model calls
  pays less; a session with a single short call can pay slightly more. No
  saving has been measured by Flywheel.
- The `usage` object of `flywheel code -p --output-format json`, and the saved
  session's usage, can carry two new fields, `cache_read_tokens` and
  `cache_write_tokens`. They appear only when a provider reported them. This
  applies to OpenAI-compatible hosts and Gemini too, which cache by
  themselves.
- The harness-config ledger entry has a new field, `prompt_cache`.
- A proxy in front of Anthropic that rejects `cache_control` gets one request
  it refuses; Flywheel then sends the request again without the marks and
  stops sending them to that host.

To keep the 1.x behaviour, set `FLYWHEEL_PROMPT_CACHE=0`.

## Commands may write in the project folder

In 1.x a `run` command in `flywheel code` could read the project and could
write nowhere in it. In 2.0 a command may write in the project folder and in
its own scratch folder, so installs, builds, formatters and `git commit`
work. The rest of the disk stays closed to it.

What stays the same:

- The permission mode still decides whether a command runs at all: refused in
  `plan`, asked in `ask` and `edit`, run in `auto`. A deny rule wins over
  every mode.
- Git hooks, git config lines that start a program, and the session's
  permission, hook and MCP files are guarded. Each is compared before and
  after a command, a change is put back, and the command is reported as
  failed.
- Background jobs run with the project read-only.

What changes:

- A command can modify files in the tree outside the write tools. `/undo`
  covers the write tools and does not put back what a command wrote. Use git
  to review and revert those changes.
- On Linux and macOS a read-only project is now enforced by the sandbox. In
  1.x the folder was writable there, whatever the documentation said. A
  command that worked on those systems only because of that gap now fails
  when the project is read-only.
- Each command's result ends with one line that says whether the workspace
  was writable.

To keep the 1.x behaviour, set `FLYWHEEL_WORKSPACE_WRITES=0`. An
administrator can pin it for a machine with `{"allow_workspace_writes":
false}` in the machine policy file; the pin outranks the variable. The cases
in which the project stays read-only by itself are listed in
[the coding session page](CODE-SESSION.md), "Keeping the project read-only".

## The gateway

### The gateway answers /v1/messages itself

In 1.x the gateway passed `POST /v1/messages` through to the local serve
endpoint. That endpoint flattened the conversation into one prompt for the
local model, ignored tools, and reported word counts as usage.

In 2.0 the gateway answers the path. It routes the request to the upstream
named by the `model` field, carries tools and streaming, reports the
provider's token counts, and writes each call to the gateway ledger.

What stays the same: the path, the gateway token, and the Messages request and
response format. The serve endpoint still answers `/v1/messages` on its own
port.

What changes:

- The `model` field decides where the request goes. A gateway endpoint name
  such as `ollama:qwen2.5:1.5b` or `anthropic` is used as written. Any other
  name needs `FLYWHEEL_GATEWAY_UPSTREAM` set where the gateway runs, or the
  request is refused with 404 `not_found_error`.
- A request the old path accepted loosely is now checked. `max_tokens` is
  required, and a `tool_result` must answer a `tool_use` in the turn before it.
- `usage` holds the provider's counts. It no longer holds word counts.
- The gateway token is also accepted in the `x-api-key` header.

To reach the local model's flattened-prompt Messages endpoint as before, send
the request to the serve endpoint's own address. `docs/GATEWAY-INTERFACES.md`
describes the new behaviour in full.

### The gateway answers /v1/responses itself

In 1.x the gateway passed `POST /v1/responses` through to the local serve
endpoint. That endpoint has no Responses handler, so the request came back as
404 `not found`.

In 2.0 the gateway answers the path in the OpenAI Responses format. It routes
the request to the upstream named by the `model` field, the same way
`/v1/messages` does, and writes each call to the gateway ledger. An OpenAI
SDK client can use the gateway as its base URL, with `/v1` at the end.

What changes for a caller that relied on the old 404: the path now returns a
Response object, or an error in the OpenAI error shape. The gateway serves a
subset of the format. `previous_response_id`, built-in tools, and image and
file inputs are refused with 400 `invalid_request_error`, and the error names
the field. `docs/GATEWAY-INTERFACES.md` has the full table under "The subset".

### Usage on every served endpoint

One rule now covers every endpoint Flywheel serves. `usage` holds the
provider's token counts and never an estimate. Every reply carries
`"x_flywheel": {"usage_reported": true}` or `false`. When the provider sent no
counts, `usage` is `null` where the wire format allows it, and zeros with the
flag set to `false` where it does not.

| Endpoint | `usage` when the provider sent no counts | Flag |
|---|---|---|
| Gateway `POST /v1/chat/completions` | `null`, with `x_usage_estimate` | `x_flywheel.usage_reported` |
| Gateway `POST /v1/responses` | `null` | `x_flywheel.usage_reported` |
| Gateway `POST /v1/messages` | `input_tokens` and `output_tokens` are `0` | `x_flywheel.usage_reported` |
| Model server `POST /chat/completions` | `null`, with `x_usage_estimate` | `x_flywheel.usage_reported` |

Messages is the exception because its format requires integers. The
`anthropic` SDK 0.95.0 types both counts as required and fails validation on
`null`. The `openai` SDK 2.36.0 types `usage` as optional on a Response and on
a chat completion.

What changes from 1.x:

- The model server's own `POST /chat/completions` sent `"usage": {}`. It now
  sends `"usage": null` and the word counts under `x_usage_estimate`, or the
  model's token counts when it reported them. This replaces the line in the
  next section that says the empty object is unchanged.
- `x_flywheel` is a new field on each of the four replies. A client that
  rejects unknown fields needs to allow it.

What you need to do: read `usage` as an object or `null`, and read
`x_flywheel.usage_reported` when a zero must be told apart from a missing
count. An empty object no longer appears.

### Virtual keys on the gateway

New in 2.0, and nothing changes unless you create a key. `flywheel
gateway-key create NAME` mints a local key with a token or spend limit for a
tool that sits behind the gateway. The gateway token works as before.
Gateway ledger entries for Messages and Responses calls gain `key` and
`usage_reported`. `docs/GATEWAY-INTERFACES.md`, "Keys and budgets", has the
details.

## The `usage` field of a served response

In 1.x two responses carried whitespace word counts in `usage`, in the place
where OpenAI and Anthropic clients read tokens:

- the gateway's chat completion (`POST /v1/chat/completions`), as
  `prompt_tokens`, `completion_tokens` and `total_tokens`;
- the Messages-shaped response of the local agent and the local model server
  (`POST /v1/messages`), as `input_tokens` and `output_tokens`.

In 2.0 `usage` carries the token counts the provider reported, or it is
`null`.

| Response | 1.x `usage` | 2.0 `usage` | 2.0 word counts |
|---|---|---|---|
| Gateway chat completion | word counts | `{"prompt_tokens", "completion_tokens", "total_tokens"}` from the provider, or `null` | `x_usage_estimate` |
| Messages-shaped response | word counts | `{"input_tokens", "output_tokens"}` from the provider, or `null` | `x_usage_estimate` |

`x_usage_estimate` is
`{"method": "whitespace_words", "prompt_words": N, "completion_words": M}`.
It is always present. Its keys say words, so nothing can read it as tokens by
accident.

What stays the same:

- `x_token_usage` on the agent response. It still carries the provider's
  counts, with the cache counts when the provider sent them.
- The `usage` object of `flywheel code -p --output-format json`. It already
  held provider counts and an `uncounted_calls` figure.
- Receipts and ledger entries. Neither held the word counts.
- The local model server's own `POST /chat/completions`. Its `usage` was an
  empty object in 1.x and still is.

What you need to do:

- A script that read `usage` for a rough size now gets real token counts,
  which are larger than word counts for the same text. If you want the old
  figure, read `x_usage_estimate`.
- Handle `null`. A provider that sends no usage block, such as the local
  transformers server, gives `usage: null`. Flywheel does not fill the gap
  with an estimate that looks measured.
- The counts are the provider's own. Anthropic reports input tokens without
  the cached part and OpenAI reports them with it. Flywheel copies the figure
  and converts nothing.

## The error object of a hosted backend

When a call to a hosted model fails, the error object's `body` no longer
carries the provider's text as it arrived. It is scrubbed for key shapes. The
run budget reads the error type, code and status from a separate
`limit_fields` value.

What you need to do: a program that parsed provider text out of `body` to
find a rate-limit or quota code reads `limit_fields`. The error line for
people ends with one sentence that says whether trying again could help.
Flywheel still does not retry by itself. The local `serve` and `ollama`
backends quote their server's error text unchanged.

## Verdicts and audits

- A certificate check that reports valid and stopped on `budget` or
  `timeout` reads UNDECIDED with the reason `BUDGET_EXHAUSTED`. In 1.x the
  same result read PASS. No certificate family shipped with Flywheel stops on
  a budget, so this reaches only a family you wrote. A declared `bound` still
  passes, and a counterexample found before the budget ran out is still
  FAIL.
- `audit run` runs two starter detectors: receipt integrity and unbacked
  claims. The detector that failed a work product with no stated limit is
  removed. If you relied on that verdict, check for a `scope` list in your
  own step.

## Removed: the two old hook scripts

`scripts/hooks/wrapper_scaffold_hook.py` and
`scripts/hooks/wrapper_turn_receipt_hook.py` were marked deprecated in 1.x
and forwarded to the capture hook module. In 2.0 they forward nothing. Each
file is a stub that writes one line naming the replacement and exits 1. A
mount that still points at one captures no turn.

| 1.x mount | 2.0 mount |
|---|---|
| `python scripts/hooks/wrapper_scaffold_hook.py` | `python -P -E -m harness.capture_hooks prompt --client claude-code` |
| `python scripts/hooks/wrapper_turn_receipt_hook.py` | `python -P -E -m harness.capture_hooks stop --client claude-code` |

What you need to do:

1. Run `flywheel traces doctor`. A mount that names a removed script is
   reported as a failure with the file it was found in.
2. Run `flywheel traces hooks print-mount` and copy the lines it prints into
   that settings file, in place of the old commands. The printed lines carry
   the interpreter path for your install.
3. Run `flywheel traces doctor` again and confirm the mount passes.

The stubs stay in the repository so an old mount fails with a message that
says what to do. A missing file would fail with an interpreter error that
names no replacement.

## Changes considered for 2.0 and left alone

Each of these was reviewed for 2.0. None is a break that waits for 3.0.

| Item | Decision | Reason |
|---|---|---|
| The `utf8` charset spelling in `Content-Length` framed messages | Kept | The LSP base protocol accepts it. Removing it would refuse valid clients. |
| Records in superstack's vendored receipt format | Keep `does_not_prove` | That format belongs to superstack. Flywheel reads and writes it unchanged until superstack moves. |
| The PyPI name `flywheel-verify` | Kept | The bare name belongs to another package. The command is still `flywheel`. |
| The pin of `agent-client-protocol` below 1.0 in the Inspect contract check | Kept | The check needs the pinned interface. It is a test dependency and no installed user meets it. |
| `x_token_usage` on the agent response | Kept | It carries cache counts that the provider-shaped `usage` object has no field for. |
| The text tool protocol (`TOOL name {json}` lines) | Kept as the fallback | Local models and hosts without tool schemas need it. See "Tool calls use the provider's function calling by default". |

## How to check an upgrade

1. `flywheel --version` prints 2.0.0 or later.
2. `flywheel doctor` reports no failure it did not report on 1.x.
3. `flywheel gate` ends with `verdict=PASS rewitness=MATCH`.
4. A record from your 1.x install still explains itself: run
   `flywheel why PATH` on a receipt or a gate envelope you kept.
5. From a checkout, `python scripts/verify_compat_records.py` verifies the
   record set written by each 1.x minor and prints MATCH for every one.
6. If you mount capture hooks, `flywheel traces doctor` passes.
