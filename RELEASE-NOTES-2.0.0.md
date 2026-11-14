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
"fix before release" findings are fixed, with eight smaller ones (#462, #465,
#466, #467, #468). You will notice these:

- **The gateway ledger is a file.** It lives in `gateway-ledger/` under the
  Flywheel home and is chained across restarts. Start one gateway per
  Flywheel home: a second one on the same home refuses model calls with 500.
  Back up or remove the folder as a whole. Editing a segment makes `verify`
  fail from then on.
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
  the end is charged for what was received. Before, such a call cost the key
  nothing.
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
  2 ms of that is the ledger entry being committed to the disk. Provider
  network time, concurrency and other machines are outside the figure.
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
  without spaces. An unfinished stream is charged an estimate. A reply the
  gateway refuses after the provider answered is not charged. Set a spending
  limit at the provider as well.
- **Fees that are not tokens are not counted**, such as web search per search
  and code execution per container hour. A key cannot cause them unless its
  allow-list names the tool.
- **There is no rate, request-size or connection limit per key** beyond calls
  in flight. A key holder can send bodies up to 32 MiB and open many
  connections. Give keys to tools and people you trust.
- **Keys share one provider account.** Provider prompt caches are shared
  across keys, so a cache-read count can show one key holder that another
  caller recently sent the same prefix. Use separate provider accounts where
  that matters.
- **Other pass-through fields are not allow-listed.** A key can still set
  `service_tier`, `container`, `thinking` and other Messages fields on a
  request to an Anthropic upstream, and any `anthropic-beta` value on a
  token-count request.
- **Key totals are a running sum in a file** (`gateway-keys.json`) that any
  process of the same user can rewrite. Check them against the gateway
  ledger. Totals, in-flight counts and reservations are not shared across
  machines.
- **The gateway speaks plain HTTP on the loopback address.** For use from
  another machine put TLS in front, for example an SSH tunnel.
  [docs/GATEWAY-INTERFACES.md](docs/GATEWAY-INTERFACES.md) has the steps.
  Revoke a key that crossed a network without TLS.

### The gateway ledger and receipts

- **A gateway that stops between a provider's reply and the ledger append
  leaves no entry.** The provider billed the call and the ledger does not
  show it.
- **`verify` catches a changed byte, a removed entry and a cut line.** A
  process of the same user that rewrites a segment and its head record
  together is not detected by the files alone.
- **The receipt covers the gateway's reading of a reply, not the bytes
  delivered.** On Messages pass-through, thinking blocks, citations and
  provider tool blocks reach the client and are outside the receipt's hash.
  The hash covers the reply's text and tool calls.
- **Every refusal with a ledger entry appends one**, so a key that keeps
  sending refused requests grows the ledger. In-flight and reservation
  refusals are not recorded.

### The coding session

- **A `TOOL name {json}` line quoted in a native reply's prose runs as a
  call.** It goes through the same permission prompt as any call and is
  recorded as a call. Read the prompt before you approve, and prefer `ask` or
  `edit` mode over `auto` when the model reads text you do not trust.
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
