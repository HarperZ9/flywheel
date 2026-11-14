# Gateway interfaces

The local gateway (`flywheel up`) answers model requests in the wire formats
other tools already speak. A tool that can be pointed at a base URL can sit
behind the gateway. Each call it makes is routed to the upstream you choose,
written to the gateway's hash-chained ledger and returned with a receipt.

| Path | Format | State |
|---|---|---|
| `POST /v1/messages` | Anthropic Messages | served by the gateway |
| `POST /v1/messages/count_tokens` | Anthropic token counting | forwarded to an Anthropic upstream |
| `POST /v1/chat/completions` | OpenAI chat | served, behind a per-operation grant |
| `POST /v1/responses` | OpenAI Responses | served by the gateway, for the subset below |

The Messages and Responses paths also accept a virtual key: a local key you
mint for one tool, with a token or spend limit and a list of models. See
"Keys and budgets" at the end of this page.

## Anthropic Messages

The gateway serves `POST /v1/messages` with and without `stream`. It carries:

- text turns, with `system` as a string or as text blocks
- tool definitions, `tool_use` blocks in replies, `tool_result` blocks in requests
- `tool_choice`, `temperature`, `top_p`, `stop_sequences` and `max_tokens`
- `usage`, with `cache_creation_input_tokens` and `cache_read_input_tokens`
- streaming in the documented event order, text as the upstream sends it

### Point Claude Code at the gateway

Set the base URL and one credential variable, then start `claude`. The base
URL has no `/v1` suffix. The credential is the gateway token: the file
`gateway.token` in the Flywheel home, `~/.flywheel` by default.

```bash
export ANTHROPIC_BASE_URL=http://127.0.0.1:8799
export ANTHROPIC_AUTH_TOKEN="$(cat ~/.flywheel/gateway.token)"
```

```powershell
$env:ANTHROPIC_BASE_URL = "http://127.0.0.1:8799"
$env:ANTHROPIC_AUTH_TOKEN = Get-Content "$HOME\.flywheel\gateway.token"
```

Claude Code sends `ANTHROPIC_AUTH_TOKEN` as `Authorization: Bearer` and
`ANTHROPIC_API_KEY` as `x-api-key`. The gateway reads either header, so both
variables work. Claude Code asks for a model by its Anthropic name, for
example `claude-sonnet-5`. Tell the gateway where those names go with
`FLYWHEEL_GATEWAY_UPSTREAM`, described below. Claude Code can also be told
which model names to ask for: the connect page documents
`ANTHROPIC_DEFAULT_OPUS_MODEL`, `ANTHROPIC_DEFAULT_SONNET_MODEL` and
`ANTHROPIC_DEFAULT_HAIKU_MODEL`, and a gateway endpoint name such as
`ollama:qwen2.5:1.5b` is a valid value for each.

Run `/status` in Claude Code to confirm the base URL and the credential source.

Source for the variables and headers: the Claude Code pages
[Connect Claude Code to an LLM gateway](https://code.claude.com/docs/en/llm-gateway-connect.md)
and the [gateway compatibility guide](https://code.claude.com/docs/en/llm-gateway-protocol.md),
read 2026-11-13.

### Point an Anthropic SDK client at the gateway

```python
import anthropic

client = anthropic.Anthropic(
    base_url="http://127.0.0.1:8799",
    api_key=open("/path/to/gateway.token").read().strip(),
)
message = client.messages.create(
    model="ollama:qwen2.5:1.5b",
    max_tokens=256,
    messages=[{"role": "user", "content": "Say hello."}],
)
```

`api_key` is sent as `x-api-key`. `auth_token` is sent as
`Authorization: Bearer` and works the same way. The client also reads
`ANTHROPIC_BASE_URL`, `ANTHROPIC_API_KEY` and `ANTHROPIC_AUTH_TOKEN` from the
environment. Checked against the `anthropic` Python SDK 0.95.0.

### Which upstream answers

The `model` field picks the upstream.

- A gateway endpoint name is used as written: `anthropic`, `openai:gpt-4o`,
  `ollama:qwen2.5:1.5b`, `gemini`. `GET /v1/models` lists the names. The part
  after the first colon is the model sent upstream. Without it the endpoint's
  default model is used.
- Any other name, such as `claude-sonnet-5`, goes to the endpoint named by the
  environment variable `FLYWHEEL_GATEWAY_UPSTREAM`, set where the gateway runs.
  `FLYWHEEL_GATEWAY_UPSTREAM=anthropic` keeps the client's model name.
  `FLYWHEEL_GATEWAY_UPSTREAM=ollama:qwen2.5:1.5b` replaces it.
- With the variable unset, an unknown name is refused with 404
  `not_found_error`, and the message says how to set it.

The subscription command-line endpoints (`claude-cli`, `codex-cli`,
`opencode`) and the local `serve` endpoint take one flattened prompt. They
cannot carry tools or structured turns, so this interface refuses them with
400 `invalid_request_error`.

The upstream is called with the gateway's own credential for that endpoint,
found the way every gateway route finds it. The client's gateway token is
never sent upstream.

### What is carried

To an Anthropic upstream the request body is forwarded as received, with only
`model` replaced. The `anthropic-version` and `anthropic-beta` headers go with
it. The reply comes back as the upstream sent it, and so does each stream
event. Thinking blocks, cache marks, images, documents and fields this page
does not name all pass through.

To an OpenAI-compatible or Gemini upstream the turn is rewritten in that
upstream's format, and the reply is written back as a Message.

| Messages feature | OpenAI-compatible upstream | Gemini upstream |
|---|---|---|
| text, `system` | carried | carried |
| tools, `tool_use`, `tool_result` | carried | carried |
| `tool_choice` `auto`, `none` | carried | carried (`none` sends no tools) |
| `tool_choice` `any`, `tool` | carried | not carried |
| `disable_parallel_tool_use` | carried | not carried |
| `is_error` on a tool result | not carried | carried |
| `temperature`, `top_p`, `stop_sequences` | carried | carried |
| thinking blocks in history | dropped | dropped |
| image and document blocks, server tools | refused | refused |
| `thinking`, `metadata` and other request fields | not sent | not sent |

A refused request gets 400 `invalid_request_error` naming the block type, and
nothing is sent upstream. Gemini thought signatures are not carried, so a
Gemini model that requires them on a tool turn will refuse the follow-up
request. Claude Code puts an attribution block first in `system`. A translated
upstream receives it as text. Set `CLAUDE_CODE_ATTRIBUTION_HEADER=0` to omit it.

### Usage

`usage` holds the provider's own counts under the Messages names. No count is
estimated. For an upstream that counts cached input inside its prompt total,
`input_tokens` is that total minus the cached part, so the three input fields
add up the way the Messages format defines. A cache count the provider did not
send is `null`. When the provider sent no input or output count, both are `0`
and the body carries `"x_flywheel": {"usage_reported": false}`. A reply with
counts carries the same field set to `true`, including a reply passed through
from an Anthropic upstream. "Usage on every endpoint" below gives the rule and
why Messages sends `0` where other formats send `null`.

In a translated stream the counts arrive on the `message_delta` event, because
the upstream reports them at the end.

### Ledger and receipt

Every served call appends an `endpoint_call` entry to the gateway ledger with
the endpoint, the model reference, the prompt hash, the response hash and
`"interface": "anthropic-messages"`. The same conversation sent through
`/v1/chat/completions` leaves an entry with the same hashes. The entry also
records `usage_reported` and who made the call (`key`).

A call that fails after the upstream was contacted appends
`endpoint_call_failed` with a reason code. A request refused before any
upstream call appends nothing, with one exception: a virtual key refused for
its budget or its model list appends `endpoint_call_refused`.

The receipt rides as `x_receipt` on a plain reply and on the `message_stop`
event of a stream. Its id is also in the `x-receipt-id` response header of a
plain reply.

### Errors

Errors use the Messages error body, `{"type": "error", "error": {"type",
"message"}, "request_id"}`, with the documented status. A malformed request is
400 `invalid_request_error`. A `tool_result` that names a `tool_use_id` the
assistant turn before it did not produce is refused the same way. An upstream
error keeps its status. An Anthropic upstream's error body is returned as sent,
with secrets scrubbed, along with its `retry-after` and `x-should-retry`
headers. A stream that stops before the upstream's end marker ends with an
`event: error` event and no `message_stop`.

### Token counting

`POST /v1/messages/count_tokens` is forwarded to an Anthropic upstream and its
answer returned. For any other upstream the gateway answers 404
`not_found_error` and makes no count. Claude Code treats the endpoint as
optional and falls back to its own character-based estimate, so `/context`
shows approximate figures there.

### Authentication

These routes need the gateway token or a virtual key, in
`Authorization: Bearer` or in `x-api-key`, and a JSON content type. The Host
check that guards every gateway route applies. They do not use the
per-operation grant flow that guards `/v1/chat/completions`. A wrong or
missing credential gets the gateway's own 401 body, which the Anthropic SDK
reports as `AuthenticationError`. Virtual keys are described under "Keys and
budgets".

### Limits

- Response headers from the upstream are not copied on a successful reply.
  That includes `anthropic-ratelimit-unified-*`.
- Claude Code model discovery reads `GET /v1/models`. The gateway serves that
  path in the OpenAI list format, which was not checked against Claude Code.
- A translated stream sends a tool call's arguments in one piece when the
  upstream finishes, not as they are generated.

### What was run

Verified by replay, with no provider called: recorded requests and replies in
the documented formats go through the handler functions, and through a real
gateway on a loopback port against a loopback stub upstream. The official
`anthropic` Python SDK 0.95.0 runs `messages.create`, `messages.stream`, a
tool round trip and the typed errors against that gateway. The upstream
formats covered are OpenAI-compatible chat, Anthropic and Gemini.

Not run: any hosted provider, Claude Code itself against the gateway, and
Gemini over a real socket (its path is replay only).

One run against a real model server was done on 2026-11-14, with a local
Ollama serving `qwen2.5:1.5b` and `FLYWHEEL_GATEWAY_UPSTREAM` set to
`ollama:qwen2.5:1.5b`. The `anthropic` SDK sent three requests through the
gateway's HTTP handler on a loopback port. A plain request returned text with
`end_turn` and the server's token counts. A streamed request delivered 29
text pieces. A request with one tool and `tool_choice` `any` returned a
`tool_use` block with the arguments the prompt asked for. Each call left an
`endpoint_call` entry with `"interface": "anthropic-messages"`. This was one
run on one small model, started from the test harness and not from
`flywheel up`.

## OpenAI Responses

The gateway serves `POST /v1/responses` with and without `stream`. It carries
the part of the Responses format that coding tools use: text, instructions,
function tools, function calls and their outputs, and usage. The rest is
refused with an error that names the field or the item type. The table under
"The subset" lists every case.

### Point an OpenAI SDK client at the gateway

The base URL ends in `/v1`. The API key is the gateway token: the file
`gateway.token` in the Flywheel home, `~/.flywheel` by default.

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:8799/v1",
    api_key=open("/path/to/gateway.token").read().strip(),
)
response = client.responses.create(
    model="ollama:qwen2.5:1.5b",
    instructions="Answer in one sentence.",
    input="Say hello.",
)
print(response.output_text)
```

The client also reads both values from the environment:

```bash
export OPENAI_BASE_URL=http://127.0.0.1:8799/v1
export OPENAI_API_KEY="$(cat ~/.flywheel/gateway.token)"
```

```powershell
$env:OPENAI_BASE_URL = "http://127.0.0.1:8799/v1"
$env:OPENAI_API_KEY = Get-Content "$HOME\.flywheel\gateway.token"
```

The SDK sends the key as `Authorization: Bearer`. Pass `stream=True` to
`client.responses.create` to read the events one by one. Source for the
arguments and the two variables: the
[openai-python README](https://github.com/openai/openai-python/blob/main/README.md),
read 2026-11-14, and the `openai` Python SDK 2.36.0.

### Codex CLI

Codex CLI was not run against the gateway. Its configuration page documents a
custom provider in `config.toml` with these keys: `model_provider` set to the
provider id, and a `[model_providers.<id>]` table holding `name`, `base_url`,
`env_key` (the name of the environment variable that holds the key) and
`wire_api = "responses"`. Source:
[Codex advanced configuration](https://developers.openai.com/codex/config-advanced),
read 2026-11-14. Two things were not checked: whether Codex appends `/v1` to
`base_url`, and which tool types Codex sends. A request that carries a tool
type outside the subset is refused, and the error names the type.

### Which upstream answers

The routing rule is the one Messages uses, described under "Which upstream
answers" above. A gateway endpoint name in `model` is used as written. Any
other name, such as `gpt-5.3-codex`, goes to the endpoint named by
`FLYWHEEL_GATEWAY_UPSTREAM`. With the variable unset, an unknown name gets 404
with `param` set to `model`.

Every upstream is reached by translation. The request is rewritten in the
upstream's own format: chat completions for an OpenAI-compatible upstream,
Messages for Anthropic, `generateContent` for Gemini. The reply is written
back as a Response object. There is no pass-through path, because no upstream
the gateway knows is called on `/v1/responses`. An OpenAI upstream is called
on `/v1/chat/completions`.

### The subset

| Request feature | What the gateway does |
|---|---|
| `input` as a string | carried, as one user turn |
| `input` items of type `message`, with or without the `type` field | carried |
| `input_text` and `output_text` content parts, or a plain string | carried |
| `system` and `developer` messages in `input` | carried, joined to `instructions` as system text |
| `function_call` items | carried |
| `function_call_output` items, with a string or `input_text` parts | carried |
| `instructions` | carried |
| `tools` of type `function` | carried; `strict` is not sent |
| `tool_choice` `auto`, `none`, `required`, or one named function | carried (Gemini: only `auto` and `none`) |
| `parallel_tool_calls` | carried (not to Gemini) |
| `max_output_tokens`, `temperature`, `top_p`, `stream` | carried |
| `reasoning` items in `input` | dropped |
| `store`, `metadata`, `include`, `reasoning`, `truncation`, `user`, `prompt_cache_key`, `service_tier`, `stream_options`, and fields this table does not name | ignored |
| `previous_response_id`, `conversation` | refused |
| `background`, `prompt`, `context_management` | refused |
| `text.format` other than `text` | refused |
| tools of any other type: `web_search`, `file_search`, `computer_use_preview`, `code_interpreter`, `mcp`, `image_generation`, `custom`, and the rest | refused |
| `input_image`, `input_file`, `input_audio` and other content parts | refused |
| `item_reference` and every other item type | refused |

Notes on the choices:

- The gateway stores no responses. That is why `previous_response_id` and
  `conversation` are refused: send the whole conversation in `input`. `store`
  is accepted and has no effect, and the Response object always says
  `"store": false`. `metadata` is echoed back.
- A `reasoning` item belongs to the provider that made it, and no upstream on
  this path can read another provider's. Refusing it would end a conversation
  that began on that provider, so the item is left out and the conversation
  goes on. The gateway never returns a reasoning item itself.
- With no `max_output_tokens` the gateway sends a limit of 4096 upstream,
  because two of the three upstream formats require one. Set the field to
  raise it.
- The flat item list becomes alternating turns. A `function_call` joins the
  assistant turn before it. A `function_call_output` must come directly after
  the calls it answers.

### The Response object

A reply has one `message` item when the model wrote text, followed by one
`function_call` item per call. `status` is `completed`, or `incomplete` with
`incomplete_details.reason` set to `max_output_tokens` or `content_filter`.
`model` is the model that served the call. The request's `instructions`,
`tools`, `tool_choice`, `temperature`, `top_p` and `max_output_tokens` are
echoed.

### Usage

`usage` holds the provider's own counts. No count is estimated.
`input_tokens` is the whole prompt, cached part included, which is how the
Responses format defines it. `input_tokens_details.cached_tokens` is the
provider's cache-read count. For an Anthropic upstream the three input counts
it reports are added up to give `input_tokens`.

When the provider sent no input or output count, `usage` is `null` and the
body carries `"x_flywheel": {"usage_reported": false}`. The format allows a
missing `usage`, and the `openai` SDK types it as optional. A reply with
counts carries `"usage_reported": true`.

Inside a `usage` object the format types every count as an integer. When the
provider sent counts without a cache count, `cached_tokens` is `0` and
`x_flywheel` also carries `"cached_tokens_reported": false`.
`output_tokens_details.reasoning_tokens` is always `0`, because the gateway
does not carry a reasoning count.

### Streaming

Events arrive in the documented order, each with a `sequence_number` that
starts at 0: `response.created`, `response.in_progress`,
`response.output_item.added`, `response.content_part.added`, one
`response.output_text.delta` per piece of text as the upstream sends it,
`response.output_text.done`, `response.content_part.done`,
`response.output_item.done`, and last `response.completed` with the whole
Response object and its usage. A reply cut by the token limit ends with
`response.incomplete` in its place.

A function call adds `response.output_item.added`,
`response.function_call_arguments.delta`,
`response.function_call_arguments.done` and `response.output_item.done`. The
arguments arrive in one delta when the upstream finishes, not as they are
generated.

A stream that stops before the upstream's end marker ends with
`response.failed`. That event carries a Response object with `status`
`failed` and `error.code` `server_error`, and no `response.completed`
follows. The `openai` SDK yields this event to the caller and does not raise.

### Ledger and receipt

Every served call appends an `endpoint_call` entry to the gateway ledger with
`"interface": "openai-responses"`. The same text conversation sent through
`/v1/chat/completions` or `/v1/messages` leaves an entry with the same
hashes. The entry also records `usage_reported` and who made the call
(`key`). A call that fails after the upstream was contacted appends
`endpoint_call_failed`. A request refused before any upstream call appends
nothing, except a virtual key refused for its budget or its model list, which
appends `endpoint_call_refused`.

The receipt rides as `x_receipt` on the Response object, both in a plain body
and inside the last event of a stream. Its id is also in the `x-receipt-id`
header of a plain reply.

### Errors

Errors use the OpenAI error body, `{"error": {"message", "type", "param",
"code"}}`. A malformed or unsupported request is 400 `invalid_request_error`,
and `param` names the field, for example `input.3.call_id` or
`previous_response_id`. A `function_call_output` that names a `call_id` the
calls before it did not produce is refused the same way. An unknown model is
404. The `type` is `rate_limit_error` for 429, `service_unavailable_error`
for 503 and `server_error` for other 5xx statuses.

An upstream error keeps its status. An OpenAI-compatible upstream's error body
is returned as sent, with secrets scrubbed. Another upstream's error is
rewritten in this shape. A wrong or missing gateway token gets the gateway's
own 401 body, which the `openai` SDK reports as `AuthenticationError`.

### Authentication

The route needs the gateway token or a virtual key in `Authorization: Bearer`
and a JSON content type, like the Messages routes. It does not use the
per-operation grant flow that guards `/v1/chat/completions`.

### Where the format was read

`platform.openai.com` refused a scripted fetch on 2026-11-14, so the reference
pages there were not read. The format comes from three places: the published
OpenAPI document in
[openai/openai-openapi](https://github.com/openai/openai-openapi), the type
definitions in the `openai` Python SDK 2.36.0, which are generated from that
document, and the function-calling, streaming and error-code guides on
`developers.openai.com`.

### What was run

Verified by replay, with no provider called: recorded requests and replies go
through the handler function, and through a real gateway on a loopback port
against a loopback stub upstream, for OpenAI-compatible, Anthropic and Gemini
upstreams. The `openai` Python SDK 2.36.0 runs `responses.create`, `stream=True`,
the `responses.stream` helper, a function-call round trip and the typed errors
against that gateway. The recorded Response objects and stream events also
validate against the SDK's own models.

Not run: any hosted provider, Codex CLI, and any client other than the
`openai` Python SDK.

One run against a real model server was done on 2026-11-14, with a local
Ollama serving `qwen2.5:1.5b` and `FLYWHEEL_GATEWAY_UPSTREAM` set to
`ollama:qwen2.5:1.5b`. The `openai` SDK sent four requests through the
gateway's HTTP handler on a loopback port. A plain request returned
`completed` with text and the server's token counts. A streamed request ran
from `response.created` to `response.completed` with 10 text deltas. A
request with one function tool and `tool_choice` `required` returned a
`function_call` item, and the follow-up request carrying its
`function_call_output` returned text that used the output. Each call left an
`endpoint_call` entry with `"interface": "openai-responses"`, and the ledger
chain verified. This was one run on one small model, started from the test
harness and not from `flywheel up`.

## Usage on every endpoint

One rule covers every endpoint Flywheel serves: `/v1/messages`,
`/v1/responses` and `/v1/chat/completions` on the gateway, and the local model
server's own `/chat/completions`. `usage` holds the provider's token counts and
never an estimate. Each reply carries `"x_flywheel": {"usage_reported": true}`
or `false`, and the ledger entry of a Messages or Responses call records the
same flag as `usage_reported`, so a real zero and a missing count can be told
apart. When the provider sent no counts, `usage` is `null` where the format
allows it: chat completions and Responses. The `openai` SDK 2.36.0 types
`Response.usage` and `ChatCompletion.usage` as optional. The Messages format
does not allow it. The `anthropic` SDK 0.95.0 types `input_tokens` and
`output_tokens` as required integers and fails validation on `null`, so
Messages sends `0` for both with the flag set to `false`. The whitespace word
estimate appears only under its own name, `x_usage_estimate`, on the two chat
completion endpoints.

## Keys and budgets

A virtual key is a local credential you mint for one tool or one teammate.
It opens the three model interface paths (`/v1/messages`,
`/v1/messages/count_tokens`, `/v1/responses`) and no other gateway route. Each
key has a name, optional limits and an optional list of models, and the
gateway keeps running totals for it. The gateway token keeps working on those
paths as the owner, with no budget.

### Create a key

```
flywheel gateway-key create ci-bot --token-limit 2000000
flywheel gateway-key create teammate --spend-limit 25 --price-in 3 --price-out 15
flywheel gateway-key create linter --models claude-haiku-4-5,ollama:qwen2.5:1.5b
```

The key is printed once, by `create`, and never again. It starts with `fwk_`.
If you lose it, revoke the key and create another.

| Option | Meaning |
|---|---|
| `--token-limit N` | Refuse calls once the key has used N tokens. |
| `--spend-limit USD` | Refuse calls once the key has spent this much. Needs both prices. |
| `--price-in USD`, `--price-out USD` | Your prices per million input and output tokens. |
| `--models a,b,c` | The model names the key may send. Without it, any model. |

Flywheel ships no price table. Spend is computed from the prices you put on
the key, so a spend limit without both prices is refused at creation.

The other commands:

```
flywheel gateway-key list            # every key: state, fingerprint, totals
flywheel gateway-key show ci-bot     # one key in full, with what is left
flywheel gateway-key revoke ci-bot   # stop the key; its totals are kept
flywheel gateway-key reset ci-bot    # zero the key's running totals
```

### Give the key to a tool

The key goes where the gateway token would go. `<key>` stands for the value
`create` printed.

Claude Code:

```bash
export ANTHROPIC_BASE_URL=http://127.0.0.1:8799
export ANTHROPIC_AUTH_TOKEN="<key>"
```

The `anthropic` SDK:

```python
client = anthropic.Anthropic(base_url="http://127.0.0.1:8799", api_key="<key>")
```

The `openai` SDK:

```python
client = OpenAI(base_url="http://127.0.0.1:8799/v1", api_key="<key>")
```

The gateway reads the key from `Authorization: Bearer` or from `x-api-key`.
It is never sent upstream. The upstream call uses the gateway's own credential
for that provider, as it does for the owner.

### What is stored where

The key itself goes into the system credential store: Windows Credential
Manager, the macOS keychain, or the Secret Service on Linux. It is not written
to a file. Where no credential store is available, `create` is refused and
says which tool is missing.

`gateway-keys.json` in the Flywheel home holds the facts that are not secret:
the name, a fingerprint (the first 16 hex characters of the key's SHA-256),
the limits, prices and model list, the created time, the revoked flag and the
running totals.

The credential store decides whether a key is real. The gateway finds a
candidate by fingerprint in the file and then compares the offered key with
the stored one. A process that can write the file and nothing else cannot
mint a working key. `revoke` deletes the stored key as well as setting the
flag, so editing the flag back does not revive it.

### What counts against a limit

Totals come from the provider's own usage report for each served call.
`tokens` is every token the provider counted, each once: uncached input,
cache read, cache write and output. For a provider that counts cached input
inside its prompt total, the cached part is not added a second time.

Spend is input-side tokens (uncached input, cache read and cache write) at
the key's input price, plus output tokens at its output price. Providers
usually bill cache reads below the input price and cache writes above it, so
this figure is your own estimate of cost and not a bill.

A streamed call is charged when its stream finishes. A call that fails is
not charged. Token counting is checked against the key and never charged.

**The crossing rule.** The check runs before the call and reads the totals so
far. A call that starts under the limit runs to the end, so one call can
cross a limit. The next call is refused. The gateway does not try to predict
whether a request's `max_tokens` would fit in what is left.

**The estimate rule.** When the provider sent no token counts, the key is
charged the whitespace word estimate of the prompt and the reply, the same
figure `x_usage_estimate` names. The charge is counted apart in the key's
totals (`estimated_calls`, `estimated_tokens`) and the ledger entry carries
`"estimated": true`. Words are fewer than tokens for the same text, so an
estimated charge runs low. An unreported count is never treated as free.

### When a call is refused

A refused call sends nothing upstream. The message names the key and the
limit.

| Case | Messages | Responses |
|---|---|---|
| A limit is reached | 400 `invalid_request_error` | 429, `type` `insufficient_quota`, `code` `key_budget_exceeded` |
| The model is not on the key's list | 403 `permission_error` | 403, `code` `model_not_allowed` |
| The key is revoked or unknown | 401 | 401 |

The limit statuses follow each provider's own documentation. The Claude API
errors page says the API returns 400 when usage reaches a spend limit you
set. The OpenAI error-codes guide lists spend limits under 429 and says the
broader `error.type` can be `insufficient_quota`. Both pages were read on
2026-11-14. A limit refusal also carries `x-should-retry: false`, which stops
the official SDKs from retrying a call that cannot succeed.

A revoked or unknown key is turned away by the gateway's authentication
check, before the interface runs, so the 401 body is the gateway's own
(`{"error": "unauthorized", "reason": "bad_token"}`). Both SDKs report it as
`AuthenticationError`. No error message repeats the value that was offered.

The model list is matched against the `model` string the client sent,
exactly as written. The upstream that name resolves to is not consulted, so
list the names your tool sends.

### What the ledger shows

An `endpoint_call` entry names who made the call: `"key": "owner"` for the
gateway token, or the key's name with `key_fp`, its fingerprint. An entry for
a key also carries `charged_tokens`. `endpoint_call_failed` names the caller
the same way. A limit or model refusal appends `endpoint_call_refused` with
the interface, the key, its fingerprint and the reason (`token_limit`,
`spend_limit` or `model_not_allowed`). It carries no hashes, and it is never a
completed-call entry. No entry holds a key.

### What is not covered

- Rate limits. A key has totals, not a requests-per-minute limit.
- A provider account per key. Every key spends from the gateway's own
  credential for the upstream.
- More than one machine. The totals live in one Flywheel home. Two gateways
  on two machines do not share them.
- Changing a limit in place. Create a new key, or reset the totals.
- Two calls that start together can both pass the check and both run.
- A stream the client abandons. It is recorded as `endpoint_call_failed` with
  reason `client_disconnected` and is not charged, although the upstream may
  have billed for the part it produced.

### What was run

Verified against a real gateway on a loopback port with a stub upstream and an
in-memory credential store: exact totals from recorded provider counts on
both interfaces, streamed and not; the refusal after a crossing with no
further upstream request; ledger attribution for two keys and the owner; a
revoked key, an unknown key and a key on other routes; the model list; totals
across a new store instance and 200 parallel debits; a forged index row; the
estimate charge; and the `anthropic` and `openai` Python SDKs holding a key.
A search of the ledger, the log records, every response, the index file and
the CLI output finds the key only in the output of `create`.

Not run: any hosted provider, Claude Code or Codex CLI holding a key, and the
real system credential store.

## Overhead

On the measured machine the gateway adds a median of 1.3 to 2.0 ms to a call
made with the gateway token and 2.6 to 3.4 ms to a call made with a virtual
key, counted to the end of the reply. Those figures are from 2026-11-14, on one
Windows 11 machine, with one client sending one request at a time to a
loopback stub in place of the provider, over 30 warm calls per case. The time
to the first text of a stream is 1.2 to 1.6 ms over the stub for either
caller. More than one call in twenty took 20 to 27 ms. Those calls waited on
the gateway's own connection to the upstream: on Windows a connect made with a
timeout sometimes comes back about 15 ms late. The first call after the
gateway starts loads modules and took 62 to 66 ms more than the stub.

The figures leave out the provider's network time and TLS, the system
credential store read for a key, concurrency, connection reuse, any hosted
provider and every other machine. They are not comparable with figures
published at a request rate. The table, the method, where the time goes and
the command to rerun it are in [BENCHMARKS.md](BENCHMARKS.md), "Gateway
overhead".

After a virtual key's call is charged, the gateway on Windows opens the key
list once on a separate thread. The first open of that file after a change
waited about 6 ms on the measured machine, and it used to be the next call's
key check. Every check and every debit still reads the file.

A test holds the figure in CI: `tests/test_gateway_overhead_timing.py` fails
when the median of five warm calls is 50 ms or more over the stub, for both
interfaces, streamed and not. Its controls add 200 ms inside the gateway,
which must fail, and make the stub four times slower, which must change
nothing.
