# Flywheel 2.0.0

Released RELEASE-DATE.

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
SECURITY-WINDOW-END, 90 days after this release. [SECURITY.md](SECURITY.md)
says how to report a vulnerability privately.

## Limits

- **Task success is not measured.** How often `flywheel code` finishes a task
  on a public benchmark, against other coding agents or against the bare
  model, has not been run. The capability matrix shows which features exist.
- **The retired accuracy comparison showed no measured gain.** Verified
  inference 9 of 10 against single-shot 8 of 10, difference +0.100, 95% CI
  [-0.236, +0.420], and the two arms were not independent. No capability
  uplift is claimed.
- **No paid hosted call was made for this release.** Streaming, native tool
  calls, prompt caching and both gateway interfaces were tested by replaying
  recorded provider traffic and against a local Ollama model. A live turn per
  hosted provider, and token counts with caching on and off, were not run.
  Claude Code and Codex CLI were not run against the gateway.
- **The desktop app ships for Windows only.** macOS and Linux desktop builds
  do not exist. There is no WinGet package and no VS Code Marketplace
  listing.
- **Virtual key budgets have gaps.** The limit is checked before a call and
  charged after it, so one call can cross a limit, and calls that start
  together can all pass the check. A call with no reported counts is charged
  a word estimate, which runs low. A key has no rate limit, all keys spend
  from one provider account, and totals are not shared across machines.
  [docs/GATEWAY-INTERFACES.md](docs/GATEWAY-INTERFACES.md), "What is not
  covered", has the list.
- **The gateway speaks plain HTTP on the loopback address.** A key or the
  gateway token sent to it across a network travels in clear text.
- **On Linux and macOS the command sandbox was tested by its arguments.** No
  command was run there for the writable-workspace change.
- **Gateway overhead was measured on one Windows machine**, one request at a
  time, against a loopback stub: a median of 1.3 to 2.0 ms with the gateway
  token and 2.6 to 3.4 ms with a virtual key. Provider network time,
  concurrency and other machines are outside the figure.
- **The Homebrew and Scoop files pin 1.9.0** until the follow-up that points
  them at 2.0.0 lands. That step needs the digests PyPI publishes.

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
