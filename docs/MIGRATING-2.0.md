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
