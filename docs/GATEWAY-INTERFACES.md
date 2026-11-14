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
| `POST /v1/responses` | OpenAI Responses | not served yet, see below |

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
and the body carries `"x_flywheel": {"usage_reported": false}`.

In a translated stream the counts arrive on the `message_delta` event, because
the upstream reports them at the end.

### Ledger and receipt

Every served call appends an `endpoint_call` entry to the gateway ledger with
the endpoint, the model reference, the prompt hash, the response hash and
`"interface": "anthropic-messages"`. The same conversation sent through
`/v1/chat/completions` leaves an entry with the same hashes.

A call that fails after the upstream was contacted appends
`endpoint_call_failed` with a reason code. A request refused before any
upstream call appends nothing.

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

These routes need the gateway token, in `Authorization: Bearer` or in
`x-api-key`, and a JSON content type. The Host check that guards every gateway
route applies. They do not use the per-operation grant flow that guards
`/v1/chat/completions`. A wrong or missing token gets the gateway's own 401
body, which the Anthropic SDK reports as `AuthenticationError`.

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

A run against a local model server (Ollama) was planned and not done: the
test machine had less free memory than the run needs. So no real model server
has answered through this interface yet.

## OpenAI Responses

`POST /v1/responses` is not served by the gateway yet. The path is still
proxied to the local serve endpoint, as in 1.x. This section will describe the
Responses interface when it lands on the same turn core as Messages.
