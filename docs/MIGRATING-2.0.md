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
