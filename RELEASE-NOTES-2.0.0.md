# Flywheel 2.0.0

Released 2026-11-14.

The coding session now works the way a hosted provider expects: replies
stream, tools go through the provider's own function calling, and Anthropic
requests are marked for prompt caching. The local gateway answers the
Anthropic Messages and OpenAI Responses formats itself, so Claude Code, Codex
and both official SDKs can use it as their base URL, and it can give a tool a
key with a budget. Records say what a result covers in a `scope` field, which
replaces `does_not_prove`. Every record a 1.x release wrote still verifies
with its original bytes.

This is a major release. Some defaults changed and some outputs were renamed.
[Moving from 1.x to 2.0](docs/MIGRATING-2.0.md) lists each one with the
setting that restores the 1.x behaviour where one exists. No 1.x release
announced these changes beforehand; the
[versioning page](docs/VERSIONING.md) records that as a dated exception.

## What you can do now

- **Watch a hosted model write.** In `flywheel code`, replies from Anthropic,
  OpenAI, OpenAI-compatible hosts and Gemini print as the model writes them.
  A stream that is cut after it began fails the turn, and nothing from it is
  recorded or run. (#450)
- **Use native tool calls.** The session declares its tools to OpenAI,
  Anthropic and Gemini as JSON schemas and reads their native calls. A native
  call is recorded as the same ledger entry the text protocol wrote, so the
  record does not change. (#451)
- **Pay less for a long Anthropic session.** Requests carry prompt-cache
  marks, and `/cost` shows the cache read and write counts the provider
  reported. Flywheel has not measured the saving. (#452)
- **Run installs, builds and `git commit` from the session.** A command may
  write in the project folder and its own scratch folder. The rest of the
  disk stays closed to it. (#448)
- **Point Claude Code or the Anthropic SDK at the gateway.** `POST
  /v1/messages` is answered by the gateway, with tools, streaming and the
  provider's token counts, and routed by the `model` field to an Anthropic,
  OpenAI-compatible or Gemini upstream. (#455)
- **Point Codex or the OpenAI SDK at the gateway.** `POST /v1/responses` is
  answered in the OpenAI Responses format, for the subset listed in
  [docs/GATEWAY-INTERFACES.md](docs/GATEWAY-INTERFACES.md). (#457)
- **Give a tool a key with a budget.** `flywheel gateway-key create NAME`
  mints a local key with a token limit, a spend limit at prices you set, and
  a list of models. Each call is recorded under the key's name. (#458)
- **Check the gateway's record of calls.** The gateway keeps its ledger as
  a hash-chained file under the Flywheel home, so it survives a restart.
  `flywheel gateway-ledger verify` exits 1 on a changed byte, a removed entry
  or a line cut short. `flywheel gateway-ledger show --key NAME` lists the
  calls of one key. (#465)
- **Set what a key may do per call.** `flywheel gateway-key set NAME` sets
  the calls a key may have running at once, the largest output one call may
  ask for, and which Anthropic pass-through features it may use. (#466)
- **Keep several accounts per provider.** `flywheel setup --provider NAME
  --account LABEL`, `flywheel auth list`, `auth use` and `auth remove`. The
  system credential store is used on macOS and Linux as well as Windows.
  (#449)
- **Check a 1.x record with 2.x.** The repository holds a sealed record set
  from each 1.x minor, and `python scripts/verify_compat_records.py` verifies
  all of them. (#454)
- **Use the research and checking tools added since 1.9.0:** one receipt
  shape for every tool (`harness/spine`), `studyrun` for a preregistered
  study, `datapipe` for one data source from download to export, prompt
  redaction before a hosted model, the reviewer-independence and
  distance-to-criticality measures, and a diff-scoped mutation audit. The
  [changelog](CHANGELOG.md) has each entry.

## What changed by default

Each of these is on by default in 2.0.0. The variable beside it restores the
1.x behaviour.

| Change | Restore 1.x with |
|---|---|
| Commands in `flywheel code` may write in the project folder | `FLYWHEEL_WORKSPACE_WRITES=0` |
| Replies from hosted providers stream | `FLYWHEEL_STREAM=0` |
| Tools are declared to OpenAI, Anthropic and Gemini as JSON schemas | `FLYWHEEL_NATIVE_TOOLS=0` |
| Anthropic requests carry prompt-cache marks | `FLYWHEEL_PROMPT_CACHE=0` |

Prompt caching changes what Anthropic bills. A cache write costs more than
plain input and a cache read costs far less. A session with many model calls
pays less. A session with one short call can pay slightly more.

`/undo` covers the write tools. It does not put back what a command wrote in
the project. Use git for that.

## What the security review changed

An independent security review of the gateway and the coding session ran on
2026-11-14, before this release. Its two release blockers and its five
"fix before release" findings are fixed, with nine smaller ones (#462, #465,
#466, #467, #468, and #469 for the last of them). A second reviewer checked
the first five of those pull requests and found nine further items, three of
them marked "should fix before release". All nine are fixed (#470). A third
reviewer, who had written none of the fixes, then read #469 and #470 and
found eleven items. One blocked the release: text inside a native tool
call's arguments could run as a different call. It is fixed (#472), and so
are nine of the others (#473); the eleventh was a gap in the limits page,
now closed. The third reviewer's probe scripts were run again against the
fixed code and no longer reproduce, with one exception that the limits page
describes (calls on one key that are in flight together). #472 and #473
were tested by their author and have not had a further independent review.
You will notice these:

- **The gateway ledger is a file.** It lives in `gateway-ledger/` under the
  Flywheel home and is chained across restarts. Start one gateway per
  Flywheel home. Back up or remove the folder as a whole. Editing a segment,
  or deleting one and leaving the head record, makes `verify` fail from then
  on.
- **No ledger, no model call.** A gateway that cannot open its ledger
  answers model calls with 503 and `retry-after: 5` before it contacts a
  provider. That happens to a second gateway on the same home, or when the
  `gateway-ledger` folder cannot be written. The gateway prints at start
  whether the ledger opened: look for the `ledger` line, and for
  `LEDGER UNAVAILABLE`. A ledger that stops taking writes while the gateway
  runs (a full disk) gets the same 503 from the next call on. The one call
  that meets the failure has already reached the provider. The gateway tries
  the ledger again when a call comes in, at most once a second; when the
  write works it serves that call, and the ledger records the gap.
- **Each entry is committed to the disk before the reply is sent.** That
  commit (fsync) is on by default and took a median of 1.2 ms and 2.9 ms on
  the two drives measured. `FLYWHEEL_GATEWAY_LEDGER_SYNC=0` skips it and
  accepts that a power loss can lose the newest entries.
- **A virtual key refuses Anthropic pass-through features unless you allow
  them.** A Messages request to an Anthropic upstream that carries an
  `anthropic-beta` value, a provider-defined tool or `mcp_servers` gets 403
  naming the field. Allow them with `flywheel gateway-key set NAME
  --allow-beta a,b --allow-server-tool web_search --allow-mcp`. A key for
  Claude Code needs `--allow-beta` for the values Claude Code sends; the
  refusal names each one. The gateway token forwards everything, as before.
- **A key has an in-flight limit.** 4 calls at once by default; change it with
  `--in-flight N`. One more call gets 429 with `retry-after: 1`. Each running
  call also reserves its output limit against the key's budget.
- **An unfinished stream is charged.** A client that closes a stream before
  the end is charged for what was received: the provider's output count when
  one had arrived, else an estimate of the text, tool-call arguments and
  thinking. A client that resets its connection before the first byte is
  recorded and charged for the prompt. An estimate here is at least a
  quarter of the characters, so text without spaces is not nearly free.
  Before, such calls cost the key nothing.
- **A key's limits are read again when the request body has arrived.** A
  key that was revoked, suspended or over a limit by then is refused, even if
  the request's headers came earlier.
- **A client that goes silent during its request is disconnected after 30
  seconds.** A client that sends headers and no body gets 408 on a model
  interface. The request line and headers must arrive within those 30
  seconds, and a request body within two minutes, whether or not the client
  holds a credential. `FLYWHEEL_GATEWAY_READ_TIMEOUT` sets another number
  of seconds; `0` switches the timeout and the deadlines off. Writes have
  no timeout.
- **In a native tool turn, a `TOOL name {json}` line in the model's text does
  not run.** When the session offered its tools through the provider's
  function calling, only the provider's tool-call objects run. A line the
  model quotes from a file or a tool's output is recorded as quoted text. If
  a model writes such lines and makes no native call, it is told once to use
  the native interface. The same holds for text inside a call's arguments: a
  call is recorded on one line whatever its arguments hold, and the calls
  that run are compared with the provider's objects. If you relied on text
  TOOL lines with OpenAI, Anthropic or Gemini, set `FLYWHEEL_NATIVE_TOOLS=0`,
  which uses the text protocol as 1.x did.
- **A model moves to the text protocol only when its host says it cannot
  take tools.** The session then prints one `Notice:` line and records it.
  An error that merely mentions tools or functions no longer does this. A
  host that words the refusal in a way Flywheel does not recognize fails the
  request; set `FLYWHEEL_NATIVE_TOOLS=0` for it.
- **No key can be named `owner`.** That is the ledger's name for calls made
  with the gateway token.
- **A redirecting upstream fails.** The gateway no longer follows a redirect
  from a provider address, because that would send the provider key to the
  new host. Set the endpoint's base URL to the final address.
- **Lean child processes get a restricted environment.** A proof under check
  can no longer read a provider key or another variable from the process
  that started Lean. `LEAN_PATH`, `LEAN_SYSROOT`, `ELAN_HOME`,
  `ELAN_TOOLCHAIN`, `LEAN_NUM_THREADS` and `LEAN_STACK_SIZE_KB` still reach
  it. A custom variable you relied on does not.
- **`flywheel gateway-key clear NAME`** lifts a suspension. A key is
  suspended when a streamed reply left the gateway and its charge could not
  be recorded.

[docs/MIGRATING-2.0.md](docs/MIGRATING-2.0.md) has a section for each, and
[docs/KNOWN-LIMITS-2.0.0.md](docs/KNOWN-LIMITS-2.0.0.md) lists what the
review found and this release leaves as it is.

## What breaks, and what to do

| If you | Then |
|---|---|
| read `does_not_prove` from Flywheel JSON | read `scope` in records written by 2.0, and keep reading the older name in 1.x records. `harness.scope.scope_list(record)` reads either |
| match an exact schema string such as `flywheel.receipt/v4` | accept the new version too. All 158 rows are on the [schema page](docs/MIGRATING-2.0-SCHEMAS.md) |
| test for a `NOT_PROVES_*` code | test for the new code, which is present when the property holds. The 15 pairs are on the schema page |
| read `usage` from the gateway or the model server | it holds the provider's token counts, or `null` when the provider sent none (zeros on `/v1/messages`, with `x_flywheel.usage_reported: false`). The 1.x word counts are in `x_usage_estimate` |
| send `POST /v1/messages` to the gateway | name a gateway endpoint in `model`, or set `FLYWHEEL_GATEWAY_UPSTREAM`. `max_tokens` is required |
| relied on `POST /v1/responses` returning 404 | it now returns a Response object |
| parse the `body` of a hosted backend's error object | read `limit_fields` for the rate-limit and quota codes |
| mount `wrapper_scaffold_hook.py` or `wrapper_turn_receipt_hook.py` | mount `python -m harness.capture_hooks`. `flywheel traces doctor` names the file to change |
| wrote a certificate family that stops on a budget | a valid result that stopped on `budget` or `timeout` reads UNDECIDED, where 1.x read PASS |
| relied on the stated-limit detector in `audit run` | it is removed. Check for a `scope` list in your own step |
| run a proxy between Flywheel and a hosted provider | it must pass server-sent events, `tools` lists and `cache_control` marks, or you switch each off |

If a script parses Flywheel's JSON and you cannot change it yet, pin
`flywheel-verify<2`.

## How old records verify

You never convert a stored record. A receipt, ledger or bundle written by any
1.x release keeps its own schema version and its older field name, and 2.x
reads it with the vocabulary it was written in. A record that carries the
list under both names is refused, because no release writes one.

The evidence is in the repository: one sealed record set from each 1.x minor
(1.0.0 to 1.9.0), each written by that release as published on PyPI. The
release workflow verifies them with the built wheel before anything is
published. The check has a control: one byte changed at any of 51,084
positions must not read MATCH.

To check a record of your own after upgrading, run `flywheel why PATH` on a
receipt or a gate envelope you kept.

## What did not change

- **License.** FSL-1.1-MIT. This release converts to MIT two years after its
  publication date. What that allows is on the licensing page,
  [docs/LICENSING.md](docs/LICENSING.md).
- **Price.** The package is free to install and run. The fixed-price
  verification pilot in the README is offered on the same terms as before.
- **The verdicts.** PASS, FAIL, UNDECIDED and UNVERIFIABLE, and the MATCH and
  DRIFT recheck results.
- **The engine has no third-party runtime dependency**, and the verifier
  path uses the Python standard library alone.
- **Python 3.11 or newer.**

## Which versions get fixes

2.x gets fixes in the next release. 1.9.x gets security fixes only, until
2027-02-12, 90 days after this release. [SECURITY.md](SECURITY.md)
says how to report a vulnerability privately.

## Limits

Read these before you upgrade. The full list, with the reason each limit was
left, is in [docs/KNOWN-LIMITS-2.0.0.md](docs/KNOWN-LIMITS-2.0.0.md).

### Not measured and not run

- **Task success is not measured.** How often `flywheel code` finishes a task
  on a public benchmark, against other coding agents or against the bare
  model, has not been run. The capability matrix shows which features exist.
- **The retired accuracy comparison showed no measured gain.** Verified
  inference 9 of 10 against single-shot 8 of 10, difference +0.100, 95% CI
  [-0.236, +0.420], and the two arms were not independent. No capability
  uplift is claimed.
- **No paid call to a hosted provider was made for this release.** Streaming,
  native tool calls, prompt caching, both gateway interfaces and the security
  fixes were tested by replaying recorded provider traffic and against a
  local Ollama model. A live turn per hosted provider, and token counts with
  caching on and off, were not run. Try your own provider on a small task
  before you rely on it.
- **Claude Code and Codex CLI were not run against the gateway.** The
  `anthropic` and `openai` Python SDKs were, against a gateway on a loopback
  port with a stub upstream.
- **Gateway overhead was measured on one Windows machine**, one request at a
  time, against a loopback stub: a median of 3.5 to 4.7 ms with the gateway
  token and 4.8 to 5.4 ms with a virtual key, to the end of the reply. About
  2 ms of that is the ledger entry being committed to the disk. The figures
  were taken before the gateway read a key's row a second time (#470); that
  read took 0.16 ms on the same machine and the table was not measured again.
  It was not measured again after #473 either, which reads the request
  head line by line under a deadline and holds one lock from the row read to
  the admission; the 50 ms timing gate ran with both changes.
  Provider network time, concurrency and other machines are outside the
  figure.
  [docs/BENCHMARKS.md](docs/BENCHMARKS.md) has the table.
- **On Linux and macOS the command sandbox was tested by its arguments.** No
  command was run there for the writable-workspace change.

### What ships, and where

- **The desktop app ships for Windows only.** macOS and Linux desktop builds
  do not exist. There is no WinGet package and no VS Code Marketplace
  listing.
- **The Windows installer is built and attached separately.** It comes from
  the same tag through a second workflow, so it can appear on the release
  page after the Python package does.
- **The Homebrew and Scoop files pin 1.9.0** until the follow-up that points
  them at 2.0.0 lands. That step needs the digests PyPI publishes.

### Gateway keys and budgets

- **A budget is an operating limit, not a hard cap on a provider's bill.** A
  call that runs alone can cross a limit by its own cost, and the next call
  is refused. Calls that run together can cross it by the input each used
  beyond its reservation, over at most the key's in-flight limit. A call with
  no reported counts is charged a word estimate, which runs low for text
  without spaces. An unfinished stream is charged the provider's output
  count when one had arrived and an estimate otherwise; one abandoned before
  its first byte is charged for the prompt only, although the provider may
  bill output it had started. A reply the gateway refuses after the provider
  answered is not charged. Set a spending limit at the provider as well.
- **Fees that are not tokens are not counted**, such as web search per search
  and code execution per container hour. A key cannot cause them unless its
  allow-list names the tool.
- **There is no rate or connection limit, and no request-size limit per
  key**, beyond calls in flight. Any client that can reach the gateway's
  port can open many connections, with or without a credential, and a key
  holder can send bodies up to 32 MiB. Keep the port on loopback, and give
  keys to tools and people you trust.
- **Keys share one provider account.** Provider prompt caches are shared
  across keys, so a cache-read count can show one key holder that another
  caller recently sent the same prefix. Use separate provider accounts where
  that matters.
- **Other pass-through fields are not allow-listed.** A key can still set
  `service_tier`, `container`, `thinking` and other Messages fields on a
  request to an Anthropic upstream, and any `anthropic-beta` value on a
  token-count request. A field that changes the price of a token is not seen
  by a spend limit, which uses the prices you gave the key; a token limit is
  not affected. A token-count request is not charged and leaves no ledger
  entry.
- **Key totals and settings are in a file** (`gateway-keys.json`) that any
  process of the same user can rewrite: limits, totals, allow-lists, the
  output cap, the in-flight limit and the suspension flag. Check the totals
  against the gateway ledger. Totals, in-flight counts and reservations are
  not shared across machines.
- **Slow clients are bounded by deadlines, not by a connection cap.** A
  client that keeps sending a few bytes holds a gateway thread until the
  head deadline (30 seconds, plus at most one more read), the body deadline
  (two minutes), or two seconds after a refusal that did not read its
  body. Nothing limits how many connections a client opens. A client that
  stops reading a stream keeps its in-flight slot until it closes. Neither
  gains spend. Put a proxy with a connection limit in front of a gateway
  that clients you do not run can reach.
- **The gateway speaks plain HTTP on the loopback address.** For use from
  another machine put TLS in front, for example an SSH tunnel.
  [docs/GATEWAY-INTERFACES.md](docs/GATEWAY-INTERFACES.md) has the steps.
  Revoke a key that crossed a network without TLS.

### The gateway ledger and receipts

- **One gateway process per Flywheel home.** A second gateway on the same
  home answers every model call with 503. Give it its own `FLYWHEEL_HOME`.
- **The 503 covers the routes that write to the ledger**: `/v1/messages`,
  `/v1/messages/count_tokens`, `/v1/responses`, `/v1/chat/completions` with a
  provider endpoint, and `/api/route`. `/v1/embeddings`, the local model on
  the chat path and the gateway's own agent, companion and evaluation routes
  never wrote to this ledger and are not refused.
- **The call that meets a ledger write failure has already reached the
  provider.** Every model interface writes its entry after the provider
  answered. A plain reply is then held back and answered 500; a stream's
  text has left and its key is suspended. If the failed write left a line
  cut short, `verify` exits 1 from then on and names the recorded break.
- **A gateway that stops between a provider's reply and the ledger append
  leaves no entry.** The provider billed the call and the ledger does not
  show it.
- **A stream's text leaves before its ledger entry exists.** The entry holds
  the hash of the whole reply and is on disk before the stream's last event.
  Treat a stream without its last event as unrecorded.
- **On a pass-through stream, a reply the gateway refuses at its end has
  already reached the client.** The refusal is an error event, no receipt
  and a failed entry. Do not act on a streamed reply that has no `x_receipt`.
- **`FLYWHEEL_GATEWAY_LEDGER_SYNC=0` trades durability for speed.** A power
  loss can then lose the newest entries.
- **`verify` catches a changed byte, a removed entry, a cut line and a
  missing segment.** A process of the same user that rewrites a segment and
  its head record together, or removes the whole folder, is not detected by
  the files alone. `flywheel anchor` has an outside party witness a head.
- **The receipt covers the gateway's reading of a reply, not the bytes
  delivered.** On Messages pass-through, thinking blocks, citations and
  provider tool blocks reach the client and are outside the receipt's hash.
  The hash covers the reply's text and tool calls.
- **Every refusal with a ledger entry appends one**, so a key that keeps
  sending refused requests grows the ledger. In-flight and reservation
  refusals are not recorded.

### The coding session

- **Tool output that contains the next call's result header can move where
  one result ends and the next begins.** When one native reply holds several
  calls, the outputs can be divided at the wrong place on the way back to
  the provider. The text arrives whole and in order, and the ledger and what
  you are asked do not change. With the text protocol
  (`FLYWHEEL_NATIVE_TOOLS=0`, or a provider without function calling) a
  `TOOL` line in the model's text still runs as a call, through the same
  permission prompt as any call; prefer `ask` or `edit` mode over `auto`
  there when the model reads text you do not trust.
- **The move to the text protocol rests on the wording of a provider's
  error.** No provider documents the sentence for "this model cannot take
  tools". The phrases Flywheel accepts come from two documented Claude API
  forms and from error texts quoted in public issue reports, and were not
  checked against a live host. A host that uses one of them for another
  reason switches that model to the text protocol; the session's notice
  tells you when that happens.
- **A Lean child process can see profile and toolchain paths.** It gets the
  variables it needs to start (home and temp folders, locale, `PATH`, the
  toolchain names) and no provider key. Proof code can print those paths.
- **A removed hook wrapper exits 1 quietly.** After the upgrade, a client
  still configured with one of the two old hook paths captures nothing if it
  hides hook errors. Run `flywheel traces doctor` once after upgrading.

## Release assets

Built by the release workflow from the tag, each listed in a sums file: the
wheel and the sdist (`python-SHA256SUMS.txt`), the plugin and skill zips
(`plugin-SHA256SUMS.txt`), the source tools plugin
(`source-plugin-SHA256SUMS.txt`) and the VS Code extension
(`vscode-SHA256SUMS.txt`). The release videos are rendered and attached by a
second workflow after the release exists.

Built separately: the Windows installer (`SHA256SUMS.txt`) and the native
MCPB companion (`native-MCPB-SHA256SUMS.txt`). They come from the same tag
through the desktop workflow, which runs the installed-app acceptance, and
are attached after their sums are checked.

## Monitor rule pack

The pre-action monitor's rule pack is unchanged from 1.9.0, so a pinned
`expected_rules_digest` stays valid. `flywheel monitor owner` prints it as
`installed_rules_digest`:

```
a76b7e8995c91861e92ce2198cd62d722deede9fb8307463c68b8aa5d5cdf8c4
```
