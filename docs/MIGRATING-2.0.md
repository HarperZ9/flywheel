# Moving from Flywheel 1.x to 2.0

Draft. This page collects every change in 2.0 that can affect a script, a
config file or a habit carried over from 1.x. Sections are added as each part
of 2.0 lands, so the page is incomplete until the release.

Most people upgrade and carry on. You need this page if you parse Flywheel's
JSON output, wrap `flywheel code` in a script, or relied on a default that 2.0
changes.

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
