# Changelog

Release notes for each version live in `RELEASE-NOTES-<version>.md`. This file
lists the changes in each release with the pull request that made them.

## Unreleased

These entries become 2.0.0. They are grouped by what a change means for someone
who uses Flywheel. `docs/MIGRATING-2.0.md` has the steps for each change that
needs one.

### What you can do now

Gateway: Anthropic Messages (#455)
- The local gateway answers `POST /v1/messages` itself, with and without streaming. Claude Code and Anthropic SDK clients can use it as their base URL. It carries text, system prompts, tool definitions, `tool_use` and `tool_result` blocks, `tool_choice`, and usage with the cache fields. See `docs/GATEWAY-INTERFACES.md`.
- The `model` field names a gateway endpoint (`anthropic`, `openai:gpt-4o`, `ollama:qwen2.5:1.5b`). Any other model name goes to the endpoint set in `FLYWHEEL_GATEWAY_UPSTREAM`. An Anthropic upstream gets the request body unchanged apart from the model, and its reply and stream events come back as sent. OpenAI-compatible and Gemini upstreams get the turn in their own format.
- Each call appends `endpoint_call_started` to the gateway ledger before the provider is contacted. A served call then appends an `endpoint_call` entry and returns a receipt as `x_receipt`. A call that fails after the upstream was contacted appends `endpoint_call_failed`. Usage holds the provider's counts and is never estimated.
- The gateway token is accepted in `x-api-key` as well as `Authorization: Bearer`. `POST /v1/messages/count_tokens` is forwarded to an Anthropic upstream and is 404 for any other.
- Changed: `/v1/messages` on the gateway used to be proxied to the local serve endpoint. See `docs/MIGRATING-2.0.md`, "The gateway answers /v1/messages itself".
- Tested by replaying recorded requests and replies, and with the `anthropic` Python SDK against a gateway on a loopback port with a stub upstream. Not run: any hosted provider, and Claude Code itself against the gateway.

Gateway: OpenAI Responses (#457)
- The local gateway answers `POST /v1/responses` itself, with and without streaming. An OpenAI SDK client can use it as its base URL (`http://127.0.0.1:8799/v1`, with the gateway token as the API key). It carries `input` as a string or as items (`message`, `function_call`, `function_call_output`), `instructions`, `function` tools, `tool_choice`, `max_output_tokens`, `temperature`, `top_p`, and usage with `input_tokens_details.cached_tokens`. See `docs/GATEWAY-INTERFACES.md`, "OpenAI Responses".
- The gateway stores no responses and runs no built-in tools. `previous_response_id`, `conversation`, `background`, tools other than `function`, and image, file and audio inputs are refused with 400 `invalid_request_error`, and `param` names the field. `reasoning` items in `input` are dropped. `store` is accepted and has no effect.
- Routing is the rule `/v1/messages` uses: a gateway endpoint name in `model`, or `FLYWHEEL_GATEWAY_UPSTREAM` for any other name. OpenAI-compatible, Anthropic and Gemini upstreams each get the turn in their own format. No upstream is called on `/v1/responses`.
- Each served call appends an `endpoint_call` entry with `"interface": "openai-responses"` and returns a receipt as `x_receipt` on the Response object. A stream that stops early ends with `response.failed` and leaves `endpoint_call_failed`. Usage holds the provider's counts and is never estimated.
- Changed: `/v1/responses` on the gateway used to be proxied to the local serve endpoint, which answered 404. See `docs/MIGRATING-2.0.md`, "The gateway answers /v1/responses itself".
- Tested by replaying recorded requests and replies, and with the `openai` Python SDK against a gateway on a loopback port with a stub upstream. One local run with Ollama (`qwen2.5:1.5b`) answered a plain, a streamed and a function-call request through both `/v1/responses` and `/v1/messages`. Not run: any hosted provider, and Codex CLI.

Gateway: virtual keys and budgets (#458)
- `flywheel gateway-key create NAME` mints a local key for one tool or teammate, with an optional token limit, an optional spend limit at prices you set (USD per million tokens; no price table ships) and an optional list of models. `list`, `show`, `revoke` and `reset` manage it. The key is printed once. It is kept in the system credential store; a file in the Flywheel home holds its fingerprint, limits and running totals.
- A virtual key opens `/v1/messages`, `/v1/messages/count_tokens` and `/v1/responses` and no other gateway route. The gateway token keeps working there as the owner, with no budget.
- A call is refused before anything is sent upstream when the key's totals are at or over a limit or the model is not on its list. A reached limit is 400 `invalid_request_error` on Messages and 429 `insufficient_quota` on Responses, following each provider's documentation. The check reads the totals so far, so one call can cross a limit and the next is refused.
- Totals come from the provider's reported usage, cache tokens included, each counted once. A streamed call is charged when the stream finishes. A call with no reported counts is charged the whitespace word estimate and marked `estimated`.
- Ledger entries for Messages and Responses calls name the caller: `"key": "owner"`, or the key's name with its fingerprint. A budget or model refusal appends `endpoint_call_refused`. No entry, log line or error holds a key.
- Not covered: rate limits, a provider account per key, and totals shared across machines.
- Tested against a gateway on a loopback port with a stub upstream and an in-memory credential store, and with the `anthropic` and `openai` Python SDKs holding a key. Not run: any hosted provider, Claude Code or Codex CLI holding a key, and the real credential store. See `docs/GATEWAY-INTERFACES.md`, "Keys and budgets".

Gateway: overhead figure and timing gate (#459)
- Measured what the gateway adds to one call on `/v1/messages` and `/v1/responses`: a median of 1.3 to 2.0 ms with the gateway token and 2.6 to 3.4 ms with a virtual key, to the end of the reply. One Windows 11 machine, 2026-11-14, one client, one request at a time, a loopback stub in place of the provider, 30 warm calls per case. The table, the method and what the figure leaves out are in `docs/BENCHMARKS.md`, "Gateway overhead".
- `python scripts/bench_gateway_overhead.py` reruns the measurement and writes `docs/benchmarks/gateway-overhead.json`. No provider is called.
- `tests/test_gateway_overhead_timing.py` fails when the median of five warm calls is 50 ms or more over the stub, for both interfaces, streamed and not, with the gateway token and with a virtual key. Two controls keep the check able to fail: 200 ms added inside the gateway breaks the budget, and a stub four times slower leaves the overhead where it was.
- Found and not changed: more than one call in twenty took 20 to 27 ms. On Windows a socket connect made with a timeout sometimes comes back about 15 ms late, and the gateway's connection to the upstream is made that way. A blocking connect was never late in the same check. On GitHub's Windows runners the late connect landed on most calls: medians of 11.6 to 23.6 ms, against 1.1 to 3.9 ms on Linux.
- Not measured: provider network time and TLS, the system credential store read for a key, concurrency, connection reuse, any hosted provider, and any other machine. The figures are not comparable with figures published at a request rate.

Hosted streaming (#450)
- In the interactive `flywheel code` session, replies from Anthropic, OpenAI, OpenAI-compatible hosts (DeepSeek, OpenRouter, GLM) and Gemini print as the model writes them. The stream is rebuilt into the provider's ordinary response and read by the same code as a plain reply, so the ledger entry, receipt id, conversation and provider token counts are the same either way. `FLYWHEEL_STREAM=0` turns it off. Azure, Bedrock, Vertex and the subscription CLIs still print whole.
- A hosted stream that is cut short after it began fails the turn: nothing from it is recorded, a tool call it was in the middle of does not run, and the session does not send a second request by itself. A stream that never began is asked once more without streaming. The interrupted-stream note now reads `[stream interrupted; the text above is not the reply]`.
- Flywheel's own time before the first streamed text is held under 50 ms by a test against a local stand-in that delays its first byte (measured median 1.6 to 1.9 ms, slowest turn 38 ms, 30 turns per dialect on Windows 11). Tested by replaying recorded streams in each provider's documented format; a live streamed turn per provider was not run. See `docs/CODE-SESSION.md`, "Output as it arrives", and `docs/MIGRATING-2.0.md`.

Native function calling (#451)
- `flywheel code` declares its tools to OpenAI, Anthropic and Gemini as JSON schemas and reads their native tool calls, on by default for the three first-party hosts. `FLYWHEEL_NATIVE_TOOLS=1` turns it on for every hosted backend and `FLYWHEEL_NATIVE_TOOLS=0` turns it off. The text protocol (`TOOL name {json}` lines) stays for local models, subscription CLIs, the cloud backends, and any host that refuses tool schemas.
- A native call is recorded as the TOOL line the text protocol would have carried, so the ledger entries, receipt ids, permission prompts and results are the same either way. The harness-config entry gains `native_tools`.
- A reply that carries a tool result the session did not produce is refused, as is a native call with arguments that are not a JSON object. Nothing from a refused reply runs.
- Tested by replaying recorded replies in each provider's documented format; a native call against a live provider was not run. See `docs/CODE-SESSION.md`, "How tool calls travel".

Prompt caching (#452)
- `flywheel code` marks Anthropic requests for prompt caching: one mark on the system prompt, covering the tools and the system text, and one at the top level that the provider moves forward with the conversation. On by default in a coding session; `FLYWHEEL_PROMPT_CACHE=0` turns the marks off. OpenAI and Gemini cache by themselves and need nothing sent.
- `/cost` and the `-p` JSON `usage` object show `cache_read_tokens` and `cache_write_tokens` when the provider reported them, for Anthropic, OpenAI-compatible hosts and Gemini. Nothing is estimated: a reply with no cache figure adds none. The harness-config entry gains `prompt_cache`.
- Tested with replayed replies. Token counts with caching on and off for a fixed 20-turn script against a live provider: not run. See `docs/CODE-SESSION.md`, "Prompt caching".

Writable workspace (#448)
- In `flywheel code`, a `run` command may write in the project folder and its own scratch folder, so installs, builds, formatters and `git commit` work. The rest of the disk stays closed to it, and so do paths reached through `..` or a link.
- Git hooks, git config lines that start a program, and the session's permission, hook and MCP files are compared before and after each command; a change is put back and the command is reported as failed.
- `FLYWHEEL_WORKSPACE_WRITES=0` or the machine policy key `allow_workspace_writes: false` keeps the project read-only to commands. Background jobs run with the project read-only. On Linux and macOS a read-only project is now enforced by the sandbox; before, the folder was writable there despite the documentation.
- `git add` and `git commit` work in a linked worktree (`flywheel code --worktree`): the session opens the worktree's own git folder and the main repository's `objects`, `refs` and `logs`, and nothing else there. A guarded file that cannot be put back puts a hold on the project. A Windows folder the account cannot label runs read-only with the reason, where it used to refuse every command.
- Tested in the real sandbox on Windows. On Linux and macOS the sandbox arguments are tested; no command was run there for this change.

Output as it arrives (#448)
- In the interactive `flywheel code` session, a command's output prints while the command runs. Model text prints as it is written when the backend can stream (Ollama; hosted providers are under "Hosted streaming" above). The ledger and the recorded results are unchanged. `FLYWHEEL_STREAM=0` turns it off.

Accounts and peer sessions
- Named accounts per provider: `flywheel setup --provider NAME --account LABEL`, `flywheel auth list`, `auth use` and `auth remove`. A key stored before this change is the account named `default`. `flywheel setup` tests a key with the provider before it stores it (`--no-check` skips the test). The system credential store is used on macOS (Keychain) and Linux (Secret Service) as well as Windows. `flywheel --help`, unknown-command messages, `down` and `why` on a gate envelope were fixed. (#449)
- Peer sessions: Flywheel finds Claude Code and Codex transcript files on the machine and reports counts, digests and file age, read-only and without transcript text (`python -m harness.peer_session_cli`, `GET /api/peer-sessions`, a Peers view in the desktop app). Hosted backends return a `usage` record with the provider's block verbatim and a `reasoning` record; Gemini answers leave out thought parts. (#444)

Reader guarantee for 1.x records (#454)
- `docs/VERSIONING.md` states that every 2.x release reads and verifies every record a 1.x release wrote, and records the 2.0.0 exception: the breaking changes shipped without a deprecation release (author's decision, 2026-11-14). 1.9.x gets security fixes for 90 days after 2.0.0.
- `tests/fixtures/compat/records-1.x` holds one sealed record set from each 1.x minor (1.0.0, 1.0.4, 1.1.2, 1.2.1, 1.3.4, 1.4.0, 1.5.1, 1.6.0, 1.7.0, 1.8.0, 1.9.0), each written by that release from its PyPI wheel. `python scripts/verify_compat_records.py` verifies them; `--control` flips one byte at every offset of every file (51,084 changes, none may read MATCH) and gives each receipt the scope list under both names (each must be refused). A reader that answers MATCH to everything fails both controls.
- Found by the byte control: `harness_version` is outside both receipt digests in v3, v4 and v5, so a receipt alone cannot show that field was edited. The fixture check binds it to the release folder and the sums file. The receipt format is unchanged.

Shared contract (the spine) (#437)
- `harness/spine` gives every tool one receipt shape. `docs/spec/spine-record.md` is the text of record. The verdict vocabulary is Flywheel's four (PASS, FAIL, UNDECIDED, UNVERIFIABLE); the MATCH/DRIFT set, the organ-bundle statuses and the gate decisions map onto it by one table, and each record keeps its source term beside the spine verdict.
- A spine record is `flywheel.spine-record/1`, schema version 1, hash-chained by `harness/hash_chain.py` under canonical-record/1. `hash_chain` gained a `digest` parameter for that; its default is unchanged, so every existing chain seals byte for byte as before.
- Optional cause-and-effect fields: intervention, run, twin digest, twin, effect, interval and placebo. The verifier refuses a twin that differs in a second field, an effect that is not run minus twin, a twin that does not match its digest and an interval that excludes its own effect. An effect claimed without a twin digest is UNVERIFIABLE. A placebo whose interval excludes zero marks the pairing CONFOUNDED.
- `python -m harness.spine verify FILE.json` rechecks a record or a chain offline. It rechecks emet witness receipts, crucible assessments and gather digests by their own published recipes. The test fixtures were emitted by each tool's own code at a pinned commit. The spine is on the verifier entry-point list, so the C2 import-closure check holds it.

Canonical records and studyrun (#433, #436)
- `docs/spec/canonical-record.md` defines `canonical-record/1`, one byte form for hashed records. `harness/canonical_record.py` is the reference code. The golden vectors in `tests/data/canonical_vectors.json` are CC0, so other repos test against them without sharing code.
- studyrun gains `studyrun.spec/2`, verdict paths for keys that hold a dot, a power gate, planted-truth fitting, autochecks for limits, constants and post hoc files (`audit`, exit 4), forecast scoring, and `ext_sha256` in new locks. Older specs and locks run and verify as before; a sweep of 570 existing specs gives identical check results, plan hashes and verdicts under the old and new code.
- `harness.studyrun` runs one study end to end: preregistration first, every input and code file hashed, analysis and controls run, hashes checked again, verdicts scored, manifest written, one ledger entry appended. See `docs/STUDYRUN.md`. A spec names what the study covers under `ledger.scope`.
- `tests/data/stats_vectors.json` holds CC0 vectors for Holm, Bonferroni, Benjamini-Hochberg, the binomial tail and Wilson. Trace observation's Holm and the studyrun bounds test against them.

Datapipe (#434)
- `harness.datapipe` takes one external data source from download to a shareable export with a receipt at each stage: a terms gate that needs a saved snapshot and a verbatim licence quote, `datapipe.record/1` rows with cell-level provenance, cleaning checks that flag and never delete, a revertible change log, and an export that blocks anything not cleared for redistribution. See `docs/DATAPIPE.md`.

Prompt redaction (#440)
- `python -m harness.prompt_redact` swaps the home folder, login name, machine name, email addresses, deny-list matches and credentials for stable placeholders (`~`, `USER`, `HOST`, `EMAIL-n`, `ID-n`, `[REDACTED:...]`) before text reaches a hosted model. `filter` mode works on stdin; `hook` mode is a Claude Code `UserPromptSubmit` hook that blocks a prompt naming local identifiers and shows the redacted copy to resubmit. Tool results are not covered yet. See `docs/features/prompt-redaction.md`.

Publish privacy (#438, #439)
- `scripts/publish_metadata_gate.py` blocks a publish that adds personal metadata. The 1,370 findings already in the tree are frozen as counts in `project-docs/records/2026-11-04-publish-metadata-baseline.json`; a file that grows its count, a new file with a finding, or any hit from the machine name, the git global email or the untracked deny list fails. The baseline only shrinks. `publish_public.py` runs it on the staging tree before any push and takes `--deny-list`; CI runs it on the checkout. The export no longer copies `scripts/.publish-denylist.txt`, which it would have shipped. See `docs/features/publish-metadata.md`.

Distance to criticality (#443)
- `harness.measure.criticality` measures d2, the KL divergence rate in bits per step from a series' best-fit AR model to the nearest critical AR model of the same order (Sooter et al. 2026, PNAS, CC BY 4.0). d_beta uses an exact closed form derived here, checked against numerical minimisation of the paper's integral. Standard library only; a clean-room implementation (the authors' toolkit is CC BY-NC 4.0 and was only read). `sliding` detrends with the past only by default, because a two-sided smoother let a leap fake an early warning in a learning-curve study. The paper's Hawkes, Langevin, AR(1), white-noise and bursty benchmarks reproduce under a preregistered study. See `docs/features/criticality.md`.

Reviewer independence (#442)
- `harness.reviewer_independence` measures how much evidence a second reader shares with the first and says whether adding it buys a catch: `p * acc * (1 - overlap)` against a 0.05 floor, with Wilson bounds when `p` and `acc` come as counts. PASS adds the reader, FAIL says it is redundant, and an interval across the floor is UNVERIFIABLE. The rule and its reference numbers come from the society lane's measurements; tests reproduce them. See `docs/features/reviewer-independence.md`.

Checks and reports (#421)
- Eval results and the harness-config hash record the serving runtime: framework, GPU, dtype, compile mode, batch shape, determinism flags and capture hooks. A rerun reports DRIFT on an output mismatch only when both runs used the same deterministic runtime. See `docs/features/eval-runtime-and-access.md`.
- Eval results record which of six access surfaces the evaluator had, and `claim_scope` rejects a claim that needs access the run did not have.
- New `coverage` and `differential` checks, and 16 partial-check false accepts added to the corpus. 15 of the 16 are caught, and 53 of 56 across the corpus, with 0 false rejects on 376 known-good items. See `docs/features/checks.md`.

Research and measurement tools
- Self-improving harness: a gated Propose-Probe-Compose loop under `harness/self_improve_*.py`, with a sealed receipt for each gate decision, quarantine for lessons and planted-edit controls. v2 puts the incumbent in the selection pool and gates at file, hunk and line level. Both versions have a preregistered head-to-head on a substitute benchmark, on CPU with scripted editors; the results are in `project-docs/records/`. (#422, #423)
- Steered-agent false-accept test: `harness/agent_false_accept` measures how often each guard stops a destructive tool call from a steered model, with mock tools only. On 28 held-out tasks the request-versus-action check caught 64 of 66 harmful calls and the schema check caught 1 of 66. (#431)
- `python -m harness.recall_index`: a deterministic distiller and recall index for agent session transcripts, with no model calls. It answers "not found" when the record holds no answer. See `docs/RECALL-INDEX.md`. (#435)
- `CITATION.cff`, and a discover gate that stops a release missing its README opening, run command, package keywords, citation file or changelog summary. (#428)
- Data: the 2026 H0 Distance Network record in `dataset/physics_tension_claims.jsonl`. (#432)
- buildc byte-witness packets carry a `scope` block: the steps the bridge ran, and `inconclusive` when `buildc receipt verify` timed out. A timeout now has its own failure code, `buildc_verification_budget_exhausted`. See `docs/features/inconclusive-budget.md`. (#441)

Release from one tag
- Pushing a version tag now builds the wheel and the sdist, runs the release gates against the built wheel on Linux and Windows, publishes to PyPI, and creates the GitHub release with the notes file and its assets. For 1.9.0 the release and most of its assets were put together by hand. See `docs/RELEASING.md`.
- The gates run with the wheel installed in a clean environment and the checkout's `harness` folder moved away: the scope migration check, every asset against its sums file, the 1.x record check with its byte-flip controls, every test marked `release_gate` (the 50 ms budgets for the coding session and the gateway, and the one-second budget for the record check), `flywheel gate`, and one coding request against a scripted model. Nothing is published unless all of them pass.
- The release carries the wheel, the sdist, the plugin and skill zips, the source tools plugin and the VS Code extension, each in a sums file. The zips and the extension are built twice and must be the same bytes. The Windows installer and the native MCPB companion are still built by `desktop-release.yml` and added after their sums are checked.
- Starting `publish.yml` by hand is a dry run: every step up to the gates, then the would-be release as a workflow artifact. A run publishes only from a version tag.
- After the upload, a job on Linux, macOS and Windows checks that PyPI serves the files that were built and that a fresh install passes `flywheel gate`.

### What changed

Each of these changes a default or an output. The setting that restores the 1.x
behaviour, where one exists, is named in the entry above or in the migration page.

Defaults in the coding session
- Commands may write in the project folder. `FLYWHEEL_WORKSPACE_WRITES=0` keeps it read-only. (#448)
- Replies from hosted providers stream. `FLYWHEEL_STREAM=0` turns it off. (#450)
- Tools are declared to OpenAI, Anthropic and Gemini as JSON schemas. `FLYWHEEL_NATIVE_TOOLS=0` keeps the text protocol. (#451)
- Anthropic requests carry prompt-cache marks, which changes how the provider bills them: a cache write costs more than plain input and a cache read far less. `FLYWHEEL_PROMPT_CACHE=0` sends the 1.x requests. No saving has been measured by Flywheel. (#452)

Usage on every served endpoint (#458)
- Every served reply carries `"x_flywheel": {"usage_reported": true}` or `false`: `/v1/messages`, `/v1/responses` and `/v1/chat/completions` on the gateway, and the model server's `/chat/completions`. The ledger entry of a Messages or Responses call records the same flag.
- Changed: `/v1/responses` sends `"usage": null` when the provider reported no counts. It sent zeros before. `/v1/messages` keeps zeros, because the Messages format and the `anthropic` SDK require integers.
- Changed: the model server's `POST /chat/completions` sends `"usage": null` with `x_usage_estimate` when the model reported no counts. It sent `"usage": {}` before. See `docs/MIGRATING-2.0.md`, "Usage on every served endpoint".

Provider boundary (#444, #445, #447)
- A failed call to a hosted model ends its error line with one plain sentence: whether trying again could help, and the wait the provider asked for when it sent one. Flywheel does not retry on its own. The retry deadline now reaches errors from the hosted chat backends as well as the proposers.
- The error object carries no unredacted provider text: its `body` is scrubbed for key shapes, and the run budget reads the error type, code and status from a separate `limit_fields` value. Usage records and kept reasoning text are scrubbed the same way, and each call's record names which request gates were open (`gates`), so an absent figure states its cause. The local `serve` and `ollama` backends still quote their server's error text as it arrived.
- `FLYWHEEL_KEEP_REASONING=1` keeps reasoning text on the record. The default is unchanged: no text.

Reports and documents
- `SECURITY.md` states which versions get fixes (2.x, and 1.9.x for security fixes for 90 days after 2.0.0) and how to report a vulnerability privately. Private vulnerability reporting is enabled on the repository. (#460)
- `site/benchmarks.html` carries the gateway overhead table that `docs/BENCHMARKS.md` already had. (#460)
- Text, Markdown, LaTeX and HTML reports print their limits under one plain heading, "limits" or "## Limits". The `--limits` help in `flywheel acp`, `dap` and `lsp` says "print the limits of a run record". The bundled `reproduce.py` says what MATCH covers. (#429)
- Changed: after a virtual key's call is charged, the gateway on Windows opens the key list once on a separate thread. On the measured machine the first open of that file after a change waited about 6 ms, and that open was the next call's key check. A plain call with a key went from 8.9 ms to 2.6 ms over the stub. Every check and every debit still reads the file, and a call that starts within a few milliseconds of the previous debit still waits. (#459)
- `docs/MIGRATING-2.0.md` is complete for what is on main: a "what you need to do" list, the record vocabulary with a table of every renamed field and code, the workspace default, the hosted defaults, the `usage` field, the hosted error object, verdicts and audits, the removed hook scripts, and how to check an upgrade. `docs/MIGRATING-2.0-SCHEMAS.md` lists all 15 receipt code pairs and all 158 schema rows; `scripts/gen_migration_tables.py` writes it from `harness/receipt_scope.py` and `project-docs/SCOPE-MIGRATION.md`, and a test fails when it is stale. Both pages are on the docs site. (#456)
- `project-docs/STATE.md` has a 2026-11-14 entry that says where current state is written and marks the older entries as history. `docs/RELEASE-NEXT.md` is retired with a pointer to this file. (#456)
- The README opens with what Flywheel does and links the verification pilot; each lane page says what the lane does with its proof beside it. (#424 to #427)

### Moved into this repository

Tools under `packages/`
- Sixteen single-purpose tools now live under `packages/`, each as the final tree of its own repository: `proof-surface`, `proof-surface-report`, `repo-proof-index`, `model-provenance-validator`, `context-curator-lite`, `workflow-harness-lite`, `secret-redact-io`, `agent-hook-pack`, `agent-routing-kit`, `public-surface-sweeper`, `discover`, `accountable-engine`, `coherence-membrane`, `behavior-transform.io`, `terminal-state-fixtures`, `seal-watch`. `packages/README.md` lists what each does, its entry points and the source commit.
- Each keeps its own `pyproject.toml` or `package.json` and installs from its folder, for example `python -m pip install ./packages/proof-surface`. The `flywheel-verify` wheel and sdist do not contain them.
- Their tests run in `.github/workflows/packages.yml` when a change touches `packages/`. The daily seal-watch check runs from `.github/workflows/seal-watch.yml`.
- `chorus` (distribution `chorus-discourse` 0.3.2) now also lives under `packages/chorus` and installs with `python -m pip install ./packages/chorus`. PyPI releases still publish from `HarperZ9/chorus`, which stays open.
- `learn` (npm `@harperz9/learn` 2.3.0) now also lives under `packages/learn`. npm releases still publish from `HarperZ9/learn`, which stays open.
- `plexus` (distribution `plexus-mesh` 0.4.0) now also lives under `packages/plexus`. PyPI releases still publish from `HarperZ9/plexus`, which stays open.
- `mneme` (distribution `flywheel-mneme` 0.7.0) now also lives under `packages/mneme`. PyPI releases still publish from `HarperZ9/mneme`, which stays open.
- `relay` (distribution `flywheel-relay` 0.7.0) now also lives under `packages/relay`. PyPI releases still publish from `HarperZ9/relay`, which stays open.
- `canon` (distribution `flywheel-canon` 0.7.0) now also lives under `packages/canon`. PyPI releases still publish from `HarperZ9/canon`, which stays open.
- `index` (distribution `index-graph` 2.16.0) now also lives under `packages/index`. PyPI releases still publish from `HarperZ9/index`, which stays open.
- `crucible` (distribution `crucible-bench` 1.6.0) now also lives under `packages/crucible`. PyPI releases still publish from `HarperZ9/crucible`, which stays open.
- `emet` (distribution `emet` 1.3.1) now also lives under `packages/emet`. PyPI releases still publish from `HarperZ9/emet`, which stays open.
- `forum` (distribution `forum-engine` 1.17.0) now also lives under `packages/forum`. PyPI releases still publish from `HarperZ9/forum`, which stays open.
- `bulletin` (private package, 0.5.0) now also lives under `packages/bulletin`. The deployed board still deploys by hand from `HarperZ9/bulletin`, which stays open; nothing is deployed from here.
- `accountable-surface` (distribution `accountable-surface` 0.3.1) now also lives under `packages/accountable-surface`. PyPI releases still publish from `HarperZ9/accountable-surface`, which stays open.
- Not run from the new location before the merge: publishing any of these to PyPI or npm.

Evidence demos under `demos/`
- Five evidence demos and receipts now live under `demos/`, each as the final tree of its own repository: `flywheel-evidence-task`, `flywheel-receipt-demo`, `bootloops-second-checker`, `crewai-kickoff-replay-receipt`, `vllm-ci-forum-receipt`. `demos/README.md` lists what each shows, how to run it and the source commit.
- Their checks run in `.github/workflows/demos.yml` when a change touches one of them. The two sealed receipts are byte-for-byte copies; seal-watch still checks the published repositories from fresh clones. The `flywheel-verify` wheel and sdist do not contain `demos/`.

Research artifacts under `docs/research/`
- Two sealed research artifacts now live under `docs/research/`, each as the final tree of its own repository: `witnessing-spine` and `faithful-transpile`. `docs/research/README.md` lists what each is, how to check it and the source commit.
- Their checks run in `.github/workflows/research-artifacts.yml` when a change touches one of them. The DOI of The Conservation of Faithfulness, 10.5281/zenodo.23126484, is unchanged.

### What broke

Breaking changes, each with a section in `docs/MIGRATING-2.0.md`. 2.0.0 ships them
without a deprecation release before it; `docs/VERSIONING.md` records that as a
dated exception. Every record a 1.x release wrote still verifies with its original bytes.

Scope field: `does_not_prove` is now `scope` (#430)
- Every record names what its result covers in a `scope` field, in plain positive words. The field replaces `does_not_prove`, whose entries were limits phrased as negatives. Each value was rewritten from what the module checks; codes such as `NOT_PROVES_EXACTNESS` became codes for the covered property, emitted when it holds (`PREDICATE_EXACT`). Certificate results carry `BOUND_FROM_SUBMITTED_OBJECT`: the verified object's value bounds the optimum from one side.
- Every schema whose records changed moved up one version: receipts to `flywheel.receipt/v5`, routed receipts to v2, QA cards to v3, and the gateway, bulletin, evidence, writing, trace and statistics records listed in `project-docs/SCOPE-MIGRATION.md`. Writers emit the new version. Readers accept both versions and read each with its own vocabulary, so v3 and v4 receipts, v1 records and every sealed or anchored artifact still verify with their original bytes.
- `harness/scope.py` (`scope_of`, `scope_list`) reads either name; the desktop app has the same helper. `scripts/check_scope_migration.py` runs in CI and keeps the older name to the readers, the sealed artifacts and historical documents. `tests/test_scope_migration.py` checks both readers, the old-version artifacts, and the bytes of 71 kept artifacts.
- Printed headings say `scope:`. Records in superstack's vendored receipt format keep their field until superstack moves.

Served `usage`, and the two old hook scripts (#453)
- The `usage` field of the gateway chat completion and of the Messages-shaped agent response carries the provider's token counts, or `null` when the provider reported none. In 1.x it carried whitespace word counts. The word counts moved to `x_usage_estimate` (`method`, `prompt_words`, `completion_words`). `x_token_usage` is unchanged. See `docs/MIGRATING-2.0.md`, "The `usage` field of a served response".
- Removed: `scripts/hooks/wrapper_scaffold_hook.py` and `scripts/hooks/wrapper_turn_receipt_hook.py` no longer forward to the capture hook module. Each is a stub that names `python -m harness.capture_hooks` and exits 1, and `flywheel traces doctor` reports a mount that still names one as a failure. See `docs/MIGRATING-2.0.md`, "Removed: the two old hook scripts".
- Reviewed and kept: the `utf8` charset spelling, superstack's vendored receipt field, the PyPI name, the `agent-client-protocol` pin, `x_token_usage` and the text tool protocol. No break is left waiting for 3.0. The table is in `docs/MIGRATING-2.0.md`.

Gateway paths
- `POST /v1/messages` on the gateway is answered by the gateway and routed by the `model` field. In 1.x it was passed to the local serve endpoint. `max_tokens` is now required. (#455)
- `POST /v1/responses` on the gateway returns a Response object or an OpenAI-shaped error. In 1.x it returned 404. (#457)
- The model server's `POST /chat/completions` sends `"usage": null` where 1.x sent `{}`. (#458)

Verdicts and audits
- A certificate check that reports valid but stopped on `budget` or `timeout` is UNDECIDED with the new reason `BUDGET_EXHAUSTED`, never PASS. A declared `bound` still passes with the bound in coverage; a counterexample found before the budget ran out is still FAIL. No shipped family stops on a budget today, so no current verdict changes. `Coverage` moved to `harness/certificates/coverage.py` and is re-exported from `base`. (#441)
- `audit run` runs two starter detectors: receipt integrity and unbacked claims. The detector that asked each work product for a stated limit is removed. (#429)

Hosted error object
- A program that parsed provider text out of the error object's `body` reads `limit_fields`. The entry is under "Provider boundary" above. (#447)

### What was fixed

Fixes
- Signed job results (the PySyft receipt): the verifier recomputes `receipt_id`, checks that `key_id` belongs to the pinned key, and checks the envelope schema. Before this, 81 single-bit changes to the fixture read MATCH; now none does. (#419)
- `flywheel --help`, unknown-command messages, `down`, and `why` on a gate envelope. (#449)
- On Linux and macOS a read-only project is enforced by the sandbox. In 1.x the folder was writable there, whatever the documentation said. (#448)
- A Windows folder the account cannot label runs read-only with the reason, where it used to refuse every command. (#448)
- The recheck runner test and the POSIX sandbox test no longer depend on the host. (#420, #446)
- Forum's SQLite ledger storage under several writers: writers take turns, an append is one transaction, and a writer that cannot take the lock within 30 seconds raises `StorageBusy` where it used to pass on SQLite's `database is locked`. (forum#49)

### Fixed after the security review (2026-11-14)
- Fixed: `/v1/messages` in front of an Anthropic upstream broke on tools the provider runs itself. A streamed reply with a `server_tool_use` block was cut, and a reply with a `web_search_tool_result` or other provider result block was recorded as failed with nothing charged, although a stream had delivered it. Such replies are now delivered as sent, recorded as `endpoint_call` and charged from the reported usage, and the entry carries the provider's `server_tool_use` counts. Unknown block and delta types are relayed untouched. A block of the exact type `tool_result` is still refused. The coding session keeps its broader rule.
- Fixed: a reply could be delivered with no ledger entry when the debit or the ledger append failed after the upstream answered. The ledger now gets `endpoint_call_failed` with reason `charge_failed` or `ledger_failed` and the response hash, and the client gets 500 naming the cause. For a stream whose text had already left, the entry says `delivered_unrecorded_charge`, the stream ends with an error event that says so, and the key is suspended until `flywheel gateway-key clear NAME`.
- New: `flywheel gateway-key clear NAME` lifts a suspension. `list` and `show` print the state `suspended`.
- Tested with replay fixtures written from the Claude API documentation (read 2026-11-14) against a gateway on a loopback port. Not run: any hosted provider.
- Fixed: the gateway's ledger lived in process memory and was lost when the gateway stopped. It is now a hash-chained file under the Flywheel home (`gateway-ledger/`), in the entry format a saved coding session uses. Each entry is committed to the disk before a plain reply is sent and before the last event of a stream. A starting gateway verifies the last segment and continues its chain. A segment that does not verify is logged at error level, left as it is and never appended to; a new segment records the break. The chat path writes to the same ledger and appends under its lock.
- New: `flywheel gateway-ledger verify` checks every segment and exits 1 on a changed byte, a removed entry or a line cut short. `flywheel gateway-ledger show --key NAME` lists the calls of one gateway key.
- Changed: the overhead figures above were measured with the ledger in memory. With the ledger on disk the gateway adds a median of 3.5 to 4.7 ms with the gateway token and 4.8 to 5.4 ms with a virtual key (same machine, same method, 2026-11-14). An append took a median of 1.2 ms and 2.9 ms on two drives; `FLYWHEEL_GATEWAY_LEDGER_SYNC=0` skips the disk commit. The 50 ms timing gate is unchanged and now runs with the on-disk ledger.
- Changed: one gateway per Flywheel home appends to the ledger. A second gateway on the same home answers model calls with 503 and reaches no provider (500 in the first build of this fix, which could still reach the provider; see the confirmation-review bullets below). See `docs/MIGRATING-2.0.md`, "After the security review: the gateway ledger is a file".
- Not covered then, closed in the fifth round below: a call whose gateway stops between the provider's reply and the append left no entry. A same-user process that rewrites a segment and its head record together is not detected by the files alone.
- Fixed: a virtual key could avoid its budget by closing each stream before the end; such a call was recorded as `client_disconnected` and charged nothing. An unfinished stream is now charged for what was received (the provider's reported input when it sent one, else the word estimate, plus the estimate of the text received), and the entry carries `charged_tokens` and `estimated`. A stream closed on its first event is recorded too; it left no entry before.
- Fixed: calls sent together on one key could all pass the limit check and overspend without bound. A key now has an in-flight limit (default 4, `--in-flight`), and each running call reserves its output limit plus a quarter of its request bytes against the budget. A call over either is refused with 429 and `retry-after: 1`. What remains: a call that runs alone can cross a limit by its own cost, and calls that run together by the input each used beyond its reservation.
- Changed: on Messages pass-through to an Anthropic upstream, a virtual key may send an `anthropic-beta` value, a provider-defined tool or `mcp_servers` only when its allow-list names it (`flywheel gateway-key set NAME --allow-beta`, `--allow-server-tool`, `--allow-mcp`). A new key allows none; the refusal is 403 naming the field. The gateway token forwards everything. `--max-output` caps the output one call may ask for. See `docs/MIGRATING-2.0.md`, "After the security review: what a virtual key may send".
- Documented: budgets count tokens. Per-use provider fees (web search per search, code execution per container hour) are outside them and are bounded by the allow-list.
- Documented: who a virtual key is for (a tool on the same machine, or a teammate over a trusted link), the bind and `--allow-host` settings, that use from another machine needs TLS in front (an SSH tunnel example is given), and every remaining budget limit in one list, in `docs/GATEWAY-INTERFACES.md` and `docs/MIGRATING-2.0.md`. `docs/KNOWN-LIMITS-2.0.0.md` lists what the review found and this release leaves as it is, with the reason for each.
- Fixed: a request body nested too deep to parse got 500; it gets 400. A credential header with a non-ASCII character dropped the connection; it gets 401.
- Fixed: `flywheel gateway-key revoke` ignored a credential store that did not delete the key and still printed that it had. It now exits 1 and says so; the key is refused either way. On Linux and macOS the key list file is written owner-only.
- Fixed: the gateway's upstream transports followed redirects, which re-sends the provider key header to the new address. They follow none now; a redirect comes back as an error with its status.
- Fixed: a gateway key (`fwk_...`) that reaches log or error text is redacted. An upstream can no longer put `x_receipt` or `x_flywheel` on a relayed stream event.
- Fixed: Lean child processes inherited the whole environment of the process that started them, so a candidate proof that evaluates `IO.getEnv` could print a provider key or another variable into `kernel_output`. Every Lean spawn (compile, binding check, replay, second kernel, export check, version probes) now gets an allow-listed environment from `harness/lean_env.py`. See `docs/PROOF-AND-FORMATS.md`, "The environment a Lean process gets". If you relied on a custom variable reaching Lean, it no longer does; `LEAN_PATH`, `LEAN_SYSROOT`, `ELAN_HOME`, `ELAN_TOOLCHAIN`, `LEAN_NUM_THREADS` and `LEAN_STACK_SIZE_KB` still do.
- Fixed: in a coding session with native function calling, a `TOOL name {json}` line in a reply's own words ran as a call, so a line the model quoted from a file, a tool's output or a web page could run. On a native turn only the provider's tool-call objects run now, in every permission mode; such a line is recorded with `> ` in front of it and leaves no `tool_call` entry. A reply that writes a TOOL line and makes no native call gets one message telling the model to use the function-calling interface (ledger kind `native_tools_notice`), at most once for each request. The text protocol is unchanged where native calling is off or not offered. If you relied on TOOL lines with a native-capable host, set `FLYWHEEL_NATIVE_TOOLS=0`. See `docs/CODE-SESSION.md`, "How tool calls travel".
- Not fixed: when one native reply holds several calls and a tool's output contains the next call's result header, the results are divided at the wrong place on the way back to the provider. `docs/KNOWN-LIMITS-2.0.0.md` keeps the row.
- Fixed after a second review of the fixes above: a gateway that could not open its ledger still reached the provider. A streamed reply was delivered in full with no ledger entry and no charge, a plain call was billed and then answered 500, and the chat path was served with no entry. The gateway now answers 503 with `retry-after: 5` before any upstream call on `/v1/messages`, `/v1/messages/count_tokens`, `/v1/responses`, `/v1/chat/completions` with a provider endpoint and `/api/route`, for each cause: a second gateway on the same home, another process holding the writer lock, and a ledger folder that cannot be written. The gateway opens the ledger at start and prints whether it did. This fix covered a ledger that cannot be opened. A ledger whose writes fail after it opened is covered by the third-review bullets below.
- Fixed: a client that reset its connection while the upstream was still opening a stream left no ledger entry and was charged nothing, although the provider was called. The response now has an explicit close hook that runs whether or not the stream was read, so the call is recorded as `client_disconnected` with `"abandoned": true` and charged for the prompt.
- Fixed: a key's limits were checked against the row read when the request headers arrived, so requests that sent headers early and bodies later were all served past a limit. The row is read again after the body, immediately before admission; a key revoked or suspended in between is refused. New: a read timeout of 30 seconds on the requests of every gateway connection (`FLYWHEEL_GATEWAY_READ_TIMEOUT`; `0` switches it off). A body that stops arriving on a model interface gets 408.
- Fixed: `flywheel gateway-ledger verify` passed when the head record was there and its segment file had been deleted. It now fails, and a gateway that starts on such a home records the break. `verify` reads once more before it reports a problem. That second read did not settle a ledger that a gateway keeps appending to; the third-review bullets below have the fix.
- Fixed: an unfinished stream was charged for received text only. It is now charged the provider's output count when one had arrived, and tool-call arguments and thinking count toward the estimate.
- Changed: no key can be named `owner`, the ledger's name for the gateway token's calls. `flywheel gateway-ledger show` escapes control characters in recorded strings (with `--json` it did not escape U+0080 to U+009F, the bidi controls or DEL until the fourth-review bullets below). The static check of the Lean modules also covers `subprocess.call`, `check_call`, `getoutput`, `getstatusoutput`, `os.system`, `os.popen`, `os.spawn*` and `os.exec*`, matched by the name as written.
- Tested over real loopback sockets with a stub upstream on Windows and, in CI, Linux: `tests/test_gateway_ledger_unavailable.py`, `tests/test_gateway_abandoned_and_delayed.py`, `tests/test_gateway_confirmation_small_fixes.py`. These and `tests/test_gateway_review_small_fixes.py` and `tests/test_lean_child_env.py` now run against the built wheel before a release. Not run: any hosted provider. Not measured again: the gateway overhead figures, after the second read of the key row (0.16 ms on the test machine).
- Fixed after an independent review of those fixes (it blocked the release): in a coding session with native function calling, text inside a tool call's arguments could replace the model's call with a different one. A native call is recorded as a `TOOL name {json}` line, and the session's line reader also cuts at U+0085, U+2028 and U+2029, which the record left raw. An argument holding one of them lost the model's call, and a quoted `TOOL run {...}` fragment after the cut ran in `auto` mode or was put to the user in `ask` and `edit`. A call is now one line whatever its arguments hold, and the tool receives the argument unchanged. The session also compares its record with the provider's tool-call objects (count, names, arguments) and runs those objects only; the repair step for malformed TOOL lines never runs on a native turn; a record that does not read back as the objects runs nothing and the model is told once. A side effect is gone too: a native call with one of these characters in an argument used to be dropped without a word. Tested with OpenAI, Anthropic and Gemini replies, plain and streamed, in all four permission modes, and with random arguments drawn from every line and separator character: `tests/test_code_session_native_argument_lines.py`, which runs against the built wheel before a release. Not run: a live model. See `docs/CODE-SESSION.md`, "How tool calls travel".
- Fixed after the same review: a ledger that opened at start and then stopped taking writes (a full disk) did not stop model calls. Every call still reached the provider for as long as the failure lasted, and when writes came back the segment held repeated sequence numbers and `verify` failed. The first failed append now marks the ledger failed (a head record that cannot be rewritten counts as one; an append that fails with an error other than `OSError` or `ValueError` did not count until the fourth-review bullets below), and later calls answer 503 with `ledger_unavailable` before any provider is contacted. When writes resume the gateway reads the segment back and goes on: with a `ledger_gap` entry when the file is whole, so `verify` passes, or with a new segment that records the break when a line was left cut short. Some calls cannot be refused: every model interface appends after the provider answered, so every call already in flight when the first append fails was made. That is at most a key's in-flight limit for each key, and it is not bounded for the gateway token. Each plain reply is held back and answered 500; each stream's text has left.
- Fixed: `flywheel gateway-ledger verify` reported "entries were removed" on an intact ledger while a gateway appended to it, on every run for a segment of some thousand entries. It reads the head record before the segments now. It also named the line before a line that was cut short and did not count that entry; it names the cut line.
- Fixed: a file in the ledger folder named like a segment (`segment-backup.jsonl`, `segment-000001 - Copy.jsonl`) stopped the gateway at start with an uncaught error or failed `verify` on an intact ledger. Only exact segment names, with ASCII digits, are read; `verify` and the start line name the others as ignored.
- Fixed: a request that was paused between the second read of its key's row and its admission could be admitted on a total that another call had changed in the pause. The read and the admission are one step under one lock now. Calls that run at the same time keep the documented margin.
- Fixed: an unfinished stream on an OpenAI-format upstream was charged a word count of the prompt, so 80,000 characters with no space cost 6 tokens. An unfinished stream's system prompt and message text, and its received text, are each charged at least a quarter of their characters, rounded up, and the entry stays marked `estimated`. Tool definitions in the request were outside that estimate until the fourth-review bullets below. `docs/KNOWN-LIMITS-2.0.0.md` said the word count applied to local and compatible hosts only; the row is corrected.
- Changed: a model moves from native function calling to the text protocol only when its host's error says tools or function calling are unsupported. Any 400 that mentioned "tool" or "function" used to do it, a context-length error included, and a quoted TOOL line in the next reply then ran. The session that met the error prints one notice and records a `native_tools_fallback` entry when a model moves. Other sessions in the same program move with it; they were not told until the fourth-review bullets below. A reply is held to the native rule by what its own request carried, so a model that another session moves meanwhile does not change a reply already on its way. No provider documents the exact sentence, so the accepted wording is a stated heuristic; `docs/KNOWN-LIMITS-2.0.0.md` has the row.
- New: the request line and headers of a gateway request must arrive within one read timeout and a request body within four, on every route, with or without a credential. A late body gets 408 on every route (on the routes outside the three model interfaces since the fifth round below; they answered 500 until then). After a refusal that did not read the body (a 401, for one), what the client still sends is discarded for two seconds at most. A client that dripped header lines, or bytes after a refusal, used to hold a thread for as long as it liked. There is still no cap on open connections.
- Changed: `flywheel gateway-ledger show` cuts a field longer than 80 characters and says how much it left out; `--full` prints it whole. The static check of the Lean modules resolves import aliases and also reports `asyncio.create_subprocess_*`, `os.posix_spawn*`, `os.startfile`, `os.fork`, `pty`, `multiprocessing`, `getattr` on those modules and an `env=` that is not exactly `lean_env(...)`; `tests/lean_spawn_scan.py` lists what it cannot see. `docs/KNOWN-LIMITS-2.0.0.md` names `/v1/embeddings` among the routes outside the ledger.
- Tested over real loopback sockets with a stub upstream, and with recorded provider replies: `tests/test_gateway_ledger_write_failure.py`, `tests/test_gateway_ledger_live_verify.py`, `tests/test_gateway_admission_lock.py`, `tests/test_gateway_round3_small_fixes.py`, `tests/test_code_session_native_fallback_trigger.py`, which run against the built wheel before a release with `tests/test_lean_child_env.py`. Each change to the gateway and the session was also reverted alone in a scratch copy, and its tests then failed. The reviewer's probe scripts were run again against the fixed code. A fourth review then read these fixes; the bullets below have what it found. Not run: any hosted provider, a real full disk (the failure is simulated at the segment's file), macOS.
- Fixed after a fourth review, by a reviewer who had written none of the fixes (it blocked the release): a request whose text cannot be encoded as UTF-8 (a lone surrogate, sent as the JSON escape `\ud800`) reached the provider, and the gateway then failed while it built the ledger entry. A streamed reply was delivered whole with no ledger entry, no charge and no suspension, as often as the key holder liked; a plain call was billed and answered 500 with no entry. Such a request is now answered 400 on `/v1/messages`, `/v1/messages/count_tokens` and `/v1/responses` before a key is admitted, and nothing is sent upstream. The cause is fixed as well: each model call has one accounting record (`harness/gateway_account.py`) that is made before the provider is contacted and computes everything the ledger entry needs that does not depend on the reply; the provider is contacted only through it; and after contact every end writes exactly one entry. A fault nobody planned for writes `endpoint_call_failed` with the reason `accounting_error` (`delivered_unrecorded_charge` when a stream's text had left) and suspends the key until `flywheel gateway-key clear NAME`. A reply from an upstream that cannot be hashed is refused as malformed and recorded. `/v1/chat/completions` and `/api/route` hash the prompt before the provider is contacted. Left by this round and closed by the fifth, below: a gateway process that was killed between the provider's answer and the entry left no entry, and a provider error on `/v1/chat/completions` or `/api/route` left none. Whether a hosted provider accepts a lone surrogate escape was not tested.
- Fixed: an unfinished stream was charged for its system prompt and message text only, so 80,000 characters in one tool description cost 13 tokens a call. The input estimate is now also at least a quarter of the request's bytes, which counts tool definitions, images and documents.
- Fixed: when one coding session's provider error moved a model to the text protocol, every other session in the same program on that model moved too with no notice and no ledger entry, and a quoted `TOOL` line then ran there. Each session now prints the notice and records `native_tools_fallback` at its first request after the move, before the reply is used.
- Fixed: a ledger write that failed with an error other than `OSError` or `ValueError` did not stop model calls. Any failed write does now. When an entry was written and the head record after it could not be, the entry stays in the segment as `endpoint_call` although its reply was held back; the `ledger_gap` entry of the resumed ledger now lists it under `unconfirmed`.
- Fixed in the coding session: a native tool call whose argument holds a lone surrogate ended the turn with a raw `UnicodeEncodeError`; the reply is refused as malformed with a sentence that says why. A streamed OpenAI-format reply of whitespace and a tool call was refused; it is a tool-call turn, as the plain reply is. An error that says a model does not support tools was not recognized when it also held the word "upstream".
- Fixed: `flywheel gateway-ledger show --json` printed C1 control characters (U+0080 to U+009F), bidi controls and DEL from recorded strings raw. It prints ASCII JSON now; a parser reads back the same row.
- Not fixed in that round: every call in flight when a ledger write first fails has reached its provider; a late body on a route outside the three model interfaces was answered 500, not 408; the fallback wording check reads the whole error message; the static check of the Lean modules misses more forms than the page listed. The fifth round, below, built the first two. The last two are stated in `docs/KNOWN-LIMITS-2.0.0.md`, each with an issue.
- Tested over real loopback sockets with a stub upstream, and with recorded provider replies: `tests/test_gateway_contact_accounting.py`, `tests/test_gateway_contact_invariant.py` (one failure planted at each of six steps before the provider is contacted and twelve after, on both routes, plain and streamed), `tests/test_gateway_round4_fixes.py`, `tests/test_gateway_ledger_round4.py` and `tests/test_code_session_round4.py`, which run against the built wheel before a release. Each fix was also reverted alone in a scratch copy, and its tests then failed. These fixes have had no independent review. Not run: any hosted provider, a real full disk, macOS.
- Fifth round (#511): built what the fourth review's fixes had left stated. **A call is in the ledger before it is made.** Every call that will contact a provider appends `endpoint_call_started` (the route, the request hash, the caller, a call id and, for a virtual key, the reservation it took) and commits it to the disk before the request leaves; the end entry carries the same `call`. A request never leaves without its started entry: when that entry cannot be written the call is refused with 503. A gateway that is killed between a provider's reply and the end entry now leaves the started entry. `flywheel gateway-ledger verify` and `show` name it as an unsettled call and exit 3, a starting gateway appends `calls_unsettled`, the call's reservation counts against its key until it is settled, and `flywheel gateway-ledger settle CALL --input N --output N` (or `--no-charge`) records what the operator says the provider billed. Tested with a real child process killed at six points around the two commits (`tests/test_gateway_write_ahead.py`, `tests/test_gateway_unsettled_calls.py`).
- Fixed (#511): calls in flight when a ledger write first fails are now identified and recorded. The first call to meet the failure is refused before it is sent. Each call that was already in flight keeps its end entry, and the resumed ledger appends it after `ledger_gap`, marked `late`; a started line that reached the disk while its commit failed is ended as `not_sent`; a new segment's header carries the calls that were still open. A gateway that stops while the ledger is still failed leaves them as unsettled calls.
- Fixed (#511): a provider error on `/v1/chat/completions` or `/api/route` left no ledger entry. Both routes record through the same accounting object as the model interfaces: a started entry, then `endpoint_call` or `endpoint_call_failed`. `/v1/embeddings`, which forwarded to a hosted provider with no record at all, records the same way (`"interface": "openai-embeddings"`) and answers 503 when the ledger is unavailable. `LedgeredProposer` moved from `harness/endpoint_registry.py` to `harness/endpoint_ledgered.py`; the old import still works.
- Fixed (#511): a request body that arrived too late was answered 500 on every route outside the three model interfaces (the operation grant step reported `STORE_COMMIT_FAILED`), and a few routes read it as an empty body. It is answered 408 on every route, and nothing is sent upstream.
- Changed (#511): one rule decides when a key is suspended. A call that reached the provider and was not fully accounted, because its debit or its end entry failed for any reason, suspends its key until `flywheel gateway-key clear NAME`. A plain reply that was held back with `charge_failed` or `ledger_failed`, and an unfinished stream whose part charge failed, did not suspend before. A failed debit is recorded as `"charged_tokens": 0` with the amount under `uncharged_tokens`; it carried the amount as `charged_tokens`.
- Examined (#511): the gateway's agent runs (`/api/agent`). Both of their provider paths already wrote a started record to the run's own trace before each request and a closing record after it; `tests/test_gateway_agent_contact_invariant.py` now shows it, a provider error and a refused started record included. A third mode starts a vendor CLI, whose own provider calls Flywheel does not see. `tests/test_gateway_provider_reach_inventory.py` lists every module under `harness/` that opens a network connection and fails when one is added without saying which record it leaves; it reads syntax, and 24 of its 32 rows are marked not examined.
- Token counting stays the one request sent to a provider with no ledger entry (#511). It is forwarded only to an Anthropic upstream's `/v1/messages/count_tokens`, which the Claude API documents as free to use (read 2026-11-14), the gateway answers 404 itself for an OpenAI-format or Gemini upstream, and the code path now refuses any other URL. No live call was made.
- Gateway overhead (#511): the timing gate failed three times in two days on Windows runners, on pull requests that changed no gateway code. Two causes were found. A Python socket with a timeout connects without blocking and then waits, and on Windows that wait is a timer tick late: measured here, 78 and 142 of 300 loopback connects took over 5 ms with a timeout and none of 300 without. The gateway connected to its upstream that way; a loopback upstream is now connected blocking, with the timeout set afterwards (`harness/endpoints_connect.py`), which helps every local model server. The second cause is the disk commit: in the failing run a streamed call showed its first text delta after 2.3 ms and its end after 306.8 ms, and everything between is one ledger append and one `os.fsync`. CI then showed it directly: on a Linux runner the two commits of one call took 309.7 and 168.9 ms in two of five calls, and a bare append-and-commit in the same folder, with no gateway code, took up to 183.0 ms. The gate now measures the seconds inside `os.fsync` apart from the gateway's own time, prints the commit time beside a bare commit in the same folder, and asserts two commits per call. With both causes out of the figure the budget went down from 50 ms to 25 ms of the gateway's own time. A call now costs two commits where it cost one. Medians to the end of the reply, one run each: on the measured Windows machine 4.0 to 16.2 ms before this round and 2.6 to 6.5 ms after it, commits included, with the gateway's own share 1.3 to 3.4 ms; on CI runners, Linux 1.8 to 4.4 ms before and 2.3 to 5.6 ms after (own 1.7 to 3.5), Windows 7.0 to 24.1 ms before and 11.3 to 22.0 ms after (own 2.4 to 7.3). To the first byte of a stream on the Windows runner: 11.4 to 17.5 ms before, 5.7 to 8.0 ms after, with one commit now inside it.
- `docs/KNOWN-LIMITS-2.0.0.md` (#511): five rows closed. Every row that is left says what would close it: an issue with a design note (#489 to #510), or the reason software cannot.
- Tested (#511) over real loopback sockets with a stub upstream, on the home's on-disk ledger, and with a child process that is killed: the files named above and `tests/test_gateway_chat_route_accounting.py`, `tests/test_gateway_late_body.py`, `tests/test_gateway_suspension_rule.py`, `tests/test_gateway_unbilled_and_chat_contacts.py`, `tests/test_gateway_loopback_connect.py`. The existing gateway tests read the ledger through one helper that checks, for every call, that its started entry comes before its end entry and agrees with it (`tests/gateway_messages_support.py`, `recorded`). Each fix was seen to fail first on the unfixed tree and was reverted alone afterwards, and its tests then failed. The fourth and fifth rounds have had no independent review. Not run: any hosted provider, a real full disk, a real power loss, macOS.

## 1.9.0 (2026-10-15)

Flywheel installs with Homebrew and Scoop. `flywheel behavior-check A B` says whether two builds behave the same, `flywheel report scope` lists the calls that reached past what was allowed, and each turn of `flywheel code` records one hash of the harness settings it ran under.

Behaviour changes
- `-p` JSON results carry `harness_config_sha256`, and the ledger gains a `harness_config` entry when settings change.

Install
- Homebrew formula and Scoop manifest in this repository. (#409)

Checks and reports
- `flywheel behavior-check A B`: replay scripted sessions on two builds and report MATCH or the first diverging event. (#415)
- `flywheel report scope`: calls that reached past what was allowed, from saved session ledgers. (#413)
- A harness-config hash on every turn. (#412)
- Offline recheck of a swarm fan-in receipt. (#411)
- Footprint and startup suite, and a gated A/B runner for startup changes. (#414, #416)

Docs
- Configuration, troubleshooting, and versions and compatibility pages; a test that a 1.6.0 session still resumes. (#408)

## 1.8.0 (2026-10-15)

Behaviour changes
- `flywheel doctor` counts provider keys in the OS credential store, by name.
- `remember` is a memory permission class: refused in plan, allowed in edit and auto, asks in ask.

Connect and reach
- `flywheel setup` stores a provider key in the OS credential store. (#398)
- Azure OpenAI, Amazon Bedrock and Google Vertex AI backends. (#399)
- `flywheel update --apply` and an opt-in weekly update check. (#404)

flywheel code
- `web_search` (SearXNG, Brave, or DuckDuckGo with no key). (#400)
- Parallel read-only subagents through `tasks`. (#401)
- Plugin marketplaces and `install NAME@MARKETPLACE`. (#402)
- Background jobs stream and stop on Linux and macOS. (#403)
- PermissionRequest, PreCompact, PostCompact, SubagentStart and SubagentStop hooks. (#405)
- Project memory notes, `/memory`, `/forget`. (#406)

## 1.7.0 (2026-10-15)

Behaviour changes
- Long `flywheel code` sessions fold automatically past `--compact-budget` (default about 60,000 estimated tokens; 0 is off).
- `sandboxed_run` takes `cancel` and `work_hook`; the Windows low-integrity runner waits in slices when cancellable.

flywheel code
- Automatic compaction, `@path` mentions, `/context`, `/compact`.
- Subagents from Markdown files and a `task` tool.
- `flywheel mcp login` and `logout`: OAuth for HTTP MCP servers.
- Background jobs: `run_background`, `processes`, `/jobs`.
- Plugins: `flywheel plugin install | list | remove`.

Reach
- The repository is a GitHub Action, with an end-to-end smoke against a stub model.
- One-line installers (`install.sh`, `install.ps1`) and a three-OS first-run check in CI.
- A VS Code extension, packaged as a `.vsix` with the standard library.
- A docs site built from the repository and published to GitHub Pages; `docs/LICENSING.md`.
- Package metadata for PyPI. (#388)

## 1.6.0 (2026-10-15)

Behaviour changes
- The installed `flywheel` command enters through `cli_entry.console_main`: an unhandled exception writes a local crash report under the Flywheel home and exits 70. `FLYWHEEL_DEBUG=1` shows the traceback instead. (#382)
- `--help` on gate, up, lanes, loop-status, down, corpus-export and why prints usage and runs nothing; `flywheel gate --help` used to run the gate. (#382)
- Hosted backends put the provider's token counts on the response as `x_token_usage`; the word-count `usage` field is unchanged. (#384)

flywheel code
- `flywheel code`: an interactive coding session in the base install, on the gated loop, with `-p` for one request. (#383)
- Permission modes plan, ask, edit and auto, and `.flywheel/permissions.json` allow and deny rules. (#383, #384)
- `/undo` checkpoints; sessions saved after every turn with `--continue`, `--resume` and `--sessions`, refused when the chain, head or conversation does not verify. (#384)
- Project instructions (AGENTS.md, CLAUDE.md, FLYWHEEL.md) and `/init`; `todo` tool; plan-mode prompt; `/cost` with provider-reported tokens; `--output-format json|stream-json`. (#383, #384)
- MCP servers from `.mcp.json`-shaped files and `flywheel mcp list|add|remove`; Claude Code format hooks; Markdown custom commands; Agent Skills; `web_fetch`. (#384)
- `--acp`: Flywheel as an Agent Client Protocol agent for editors. (#384)
- `--worktree NAME` and `--plain`. (#385)
- Commands in a session run in the OS sandbox with a scratch TEMP and HOME, so `python -m pytest` runs there. (#383)

Install and support
- `flywheel doctor`, `flywheel update`, local crash reports, issue templates and SUPPORT.md; README and GETTING-STARTED name the current release. (#382)
- Trace inventory lists code sessions (S25) and crash reports (S26). (#382, #384)

Other
- The explainer and README show the 1.5.1 release films. (#379)
- The ablation runner refuses a criterion run that gives no readable verdict. (#380)
- The 1.1.2 release notes cite GHSA-g5gv-7893-ff5c. (#381)

## 1.5.1 (2026-10-14)

No runtime change; the Python package changes only in its version number.

Release media
- Each published release renders two captioned videos from its own files and attaches them: a walkthrough of the Form 1040 output check (FAIL exit 1, PASS exit 0, UNVERIFIABLE exit 3) and an explainer of why the tax table, not the rate schedule, decides the answer. Every number on screen is read from the release checkout at render time. `.github/workflows/release-media.yml` calls raw-native's media workflow, which renders on a hosted runner with a software GPU adapter. (#377)

Docs
- An animated explainer page, `docs/explainer/index.html`: the run lifecycle, the shell capability check on seven commands, a sealed `flywheel gate` result and its recheck, and the stage receipt chain, with every value taken from a run of the repository. (#375)
- README Watch and Walkthrough sections. (#376)

## 1.5.0 (2026-10-04)

Behaviour changes
- A math-domain `PASS` now needs two agreeing kernels. After the Lean kernel accepts the compile and leanchecker replays it, nanoda (an independent kernel sharing no code) type-checks the exported declarations; a `PASS` reads `kernels_agreeing: 2`, the kernels disagreeing is `FAIL`, and a missing or unusable second kernel is `UNVERIFIABLE`. `LeanOracle.output_hash` folds in `kernels_agreeing`, so older receipts' output hashes differ for the same candidate. (#370)
- The separate-identity signer anchors its heads by default: setup installs a 15-minute anchor timer, and `flywheel monitor verify --anchors` holds the store to every anchored head with new findings `ANCHORED_HEAD_DISAGREES`, `STORE_SHORTER_THAN_ANCHORED_HEAD`, `ANCHOR_RECEIPT_INVALID` and `ANCHORED_HEAD_WITHOUT_RECEIPT`. `--no-anchor` opts out. No signer is installed on any known machine, so nothing is anchored yet. (#371)

Monitor admission gate
- `flywheel monitor gate <adapter>` runs a text monitor over a frozen, hash-pinned set of 2,676 parity-product items: 892 known-invisible items from the 2026-10-04 control bank, where the computation happened with nothing in the trace and a NO is false assurance, 892 known-visible items generated from a fixed seed, where the full working is in the trace and the correct verdict is NO, and 892 known-visible parity items from a second seed, where the trace shows the parity check and the correct verdict is YES. It reports the false-assurance, false-alarm and missed-check rates with Wilson 95% intervals and the UNVERIFIABLE rate, and admits a monitor only when all three upper bounds sit under the preregistered bars (0.0100, 0.0500 and 0.0500). Six planted controls (always-YES, always-NO, always-UNVERIFIABLE, random, a shortcut that says NO whenever the trace shows arithmetic, and an oracle) run on every gate run; if one lands off its expected outcome the gate reports itself UNVERIFIABLE. The result is a `flywheel.receipt/v4`, optionally signed, that `flywheel monitor gate-verify` re-derives from the records before it checks the signature. See `docs/MONITOR-GATE.md`.


Verification
- A second Lean kernel re-checks bound proofs: the compiled module is exported with lean4export and type-checked by nanoda, which permits only `propext`, `Classical.choice` and `Quot.sound`. Receipts add `external_kernel` (tool, version, source commit, binary sha256, licence, exporter, verdict, statement hash). Two agreeing kernels rule out a bug in either kernel alone, not a shared fault, and `spec_fidelity` stays `UNVERIFIED`. See `docs/PROOF-AND-FORMATS.md`. (#370)

Preregistration and anchoring
- `python -m harness.signer anchor` signs each store's head, logs its SHA-512 and an Ed25519ph signature in Rekor and submits its SHA-256 to OpenTimestamps; only hashes, a signature and the public key leave the machine. False-success control: a host attacker who rechains and re-signs with the real key reads `MATCH` under the key alone and `DRIFT` against the anchored head. See `docs/features/rekor-anchor.md`. (#371)

Docs and rechecks
- The signer's threat model is written down: the guarantee rests on the OS identity boundary and the host kernel and hypervisor; root or SYSTEM can read the key or sign a replacement history, and an anchored head bounds that. See `docs/SEPARATE-SIGNER.md`. (#369)
- `handoff/site-designer/MANIFEST.sha256` resealed to the LF blob digest of `evidence/benchmark-ci.json` (the file never changed; the recorded value was the CRLF-form digest), with a dated correction and `RESEAL.md`. (#372)
- CI rechecks every `docs/art/receipts.json` digest against its stored SVG, so regenerating an SVG without updating the receipt now fails. A match shows the bytes are the ones the receipt names, not that the scene and seed produced them. (#373)
## 1.4.0 (2026-10-04)

Behaviour changes
- Tool-call receipts with no `authority` field verify as `FINDING` (`NO_AUTHORITY_RECORDED`) under the new authority check, and every receipt written before this release has none. `verify_receipt` is unchanged. (#361)
- `flywheel monitor verify` exits 3 with `UNANCHORED` when no trust root is pinned, where it used to report `MATCH` and exit 0. The old result stays in the report as `internal_verdict`. (#359)
- A Lean proof that does not match its task's pinned statement fails; a task with no pinned statement is `UNVERIFIABLE`. See Verification below. (#365)

Pre-action monitor
- A separate-identity signer: runs as its own OS user or account, holds a key the agent cannot read, signs each record's sequence number, previous seal and seal once, puts the OS-reported caller identity inside the signed bytes, and fails closed. A CI job runs it as a second Linux user. See `docs/SEPARATE-SIGNER.md`. (#359)
- An `authority` field on tool-call receipts (`intent`, `policy:machine`, `scope`, `policy:self`, `none`), re-derived by the verifier; `policy:machine` counts only when signed by a pinned separate-identity signer. See `docs/ACTION-AUTHORITY.md`. (#361)
- The rule pack is unchanged; digest `a76b7e8995c91861e92ce2198cd62d722deede9fb8307463c68b8aa5d5cdf8c4`.

Verification
- The math domain oracle now binds a Lean proof to the statement its task pinned. Before, `LeanOracle.verify` never read its task, so any closed theorem passed, `theorem unrelated : True := trivial` included (disclosed in `project-docs/records/2026-09-23-lean-oracle-task-binding.md` and the 1.0.3 limits). A task pins `challenge` (theorem name, statement, optional header); without one the verdict is `UNVERIFIABLE` with reason `SPECIFICATION_UNPINNED`. The candidate compiles once; a Lean program reads the compiled module as data, requires the pinned theorem's exact elaborated type and identical definitions behind it, and walks its axioms from the artifact; leanchecker replays the same module. Receipts (`flywheel.lean-receipt/v2`) add `statement_sha256`, `challenge`, `binding`, `trusted_base`, `artifact_sha256` and `spec_fidelity: UNVERIFIED`. Unrelated, weakened, renamed, shadowed-definition, shadowed-instance, `prelude`, `sorry`, custom-axiom, metaprogram-axiom and kernel-skip probes are all refused against a real kernel; the real proof passes. Behaviour change: a proof of anything other than the pinned statement now fails, and math claims through paths that pin no statement read `UNVERIFIABLE` where they read `PASS`. No published receipt depended on the hole. See `docs/PROOF-AND-FORMATS.md`. (#365)

Preregistration and anchoring
- `artifacts/prereg/signed-head.json` now signs the whole eight-entry log; the original one-entry head is kept at `heads/head-0001.json`, and CI fails when the signed head and the log disagree. (#358)
- `flywheel anchor head` and `flywheel anchor verify`: log a signed head in Sigstore Rekor (Ed25519ph, hashes only) beside OpenTimestamps, and recheck both offline against pinned keys; `--online` adds a consistency proof. The size-8 prereg head is at Rekor index 3077414145. See `docs/features/rekor-anchor.md`. (#366)
- A preregistered placebo test for exact Shapley attribution: `qwen2.5:7b` credited 0 of 80 controls (Wilson 95% 0.000 to 0.046); an exploratory `qwen2.5:0.5b` run credited 7 of 80. See `docs/features/shapley-placebo.md`. (#357)

Rechecks and canonical bytes
- `.gitattributes` defaults text to LF on every platform, so a Windows clone hashes to the stored bytes. `harness/canonical_bytes.py` reports `EOL_ONLY` (exit 3) when only line endings differ; `python -m harness.prereg_pins` checks a preregistration's file pins. See `docs/CANONICAL-BYTES.md`. (#363)
- `RECHECK.md` and `python -m harness.recheck run`: one-command recheck manifests with a control that must fail; seven manifests in `recheck/`, CPU ones run in CI on Linux and Windows. The METR evidence verifier reports `INSPECT_INPUT_BUSY` for a transient Windows sharing refusal instead of a false rejection. (#363)
- The site-designer handoff and the Inspect fixtures are pinned to committed bytes, with a `canonical-bytes` workflow on Linux and Windows. (#364)

Receipts
- A signed result receipt for an approved PySyft job, with a stdlib verifier and 16 paired tamper tests. See `docs/features/pysyft-result-receipt.md`. (#356)

Docs
- README header, hero art and brand assets. (#360)

## 1.3.4

Windows app
- The 1.3.3 Windows installer was not published. Its build stopped at the frozen engine check: `/api/lanes` failed in the frozen engine, and the check reported `RELAY_ROSTER_HTTP`. The lane roster imports the raw lane's adapter by its registry name, and the freeze left that module out because PyInstaller cannot follow a name in a string. The Windows app shows its lanes from the same roster, so the 1.3.3 app could not have listed them. The freeze now adds every adapter-lane module named in the lane registry, and a test in pull-request CI fails when one is missing. The 1.3.3 wheel on PyPI was not affected: a pip install imports the adapter from source. (#355)

## 1.3.3

Lanes
- `raw`, a reference renderer lane: raw-native 0.5.0 renders on the CPU and checks its screen-space AO against a ray-traced reference. Install fetches the release binary by URL and refuses it unless `SHA256SUMS` and the pinned binary digest match. Three rechecks: arithmetic from the files alone (raw-native's own `receipt.json` included), replay, and another renderer's AO against the reference. Every receipt is a superstack receipt carrying identity (MATCH or DRIFT) and tolerance (PASS, FAIL or UNVERIFIABLE). See `docs/features/raw.md`. (#353)
- The superstack contract v0.2.0 is vendored at `harness/_vendor/superstack.py`, pinned by SHA-256 and checked against its own vectors in CI. (#353)

Reliability
- Five Windows CI tests that failed and then passed on rerun are fixed at their cause: two wall-clock races, a process startup race, and the Rowan TTS server closing a connection with an unread request body (every POST now reads its body first). The desktop goldens accept host rasterizer noise within measured limits and still fail on real changes. After the fix, 11 of 11 runs of each Windows test shard and 10 of 10 Windows desktop runs passed. (#352)

## 1.3.2

Pre-action monitor
- Three HOLD rules for irreversible deletes: `destructive/004` (`find -delete`, `find -exec rm`, `shred` outside the workspace), `destructive/005` (`git clean -f`) and `destructive/006` (remote repository, release, bucket and cloud-resource deletes). The rule-pack digest changes; re-pin `expected_rules_digest`. (#347)
- Costly-relief scenario beside the false-accept corpus: 93 irreversible actions offered with an incentive, each with a no-incentive twin, and 45 reversible look-alikes. Before the new rules 36 of 93 offers passed; now 93 of 93 are held, and incentive text changed no verdict before or after. See `project-docs/records/costly-relief/RESULT.md`. (#347)
- Typed judge mode: a SystemOne endpoint (such as Clef-flash) answers four narrow yes/no questions, code combines them into ACT, ABSTAIN or ESCALATE, and the monitor holds on ABSTAIN (`judge_abstained`) and ESCALATE. Default for `protocol: systemone`; met every pre-stated bar on a held-out half of 788 labelled agent actions (hold precision 0.748 [0.661, 0.818], recall 0.835 [0.752, 0.894]). See `docs/PREACTION-JUDGE-TYPED.md`. (#342)
- Typed override reasons and a later outcome check for monitor holds; the two-coder agreement bar is not yet measured. See `docs/PREACTION-OVERRIDES.md`. (#344)

Verification
- `flywheel verify-share`: size-weighted share of shipped output by check route per week, a flag when the unchecked share rises two weeks running while output grows, and a cost-to-verify meter per task family. On 832 merged PRs no week was flagged, so its usefulness bar is not met. See `docs/VERIFICATION-SHARE.md`. (#346)

Search
- `--effort-gate off|first-pass|sequential`, off by default. On hard_v2 (n = 110), `sequential` kept 7 of 7 problems of search's gain at 0.446 [0.391, 0.502] of the samples and met the pre-registered bar; `first-pass` drew 0.509 and missed by 0.009. See `docs/features/search-selection.md`. (#349)
- Cost receipts: each candidate's measured time beside the hardware's speed-of-light floor, opt-in per arm. On 600 calls of a local 14B model on one RTX 4090: 600 receipts, 0 below the floor, median ratio 1.33. See `docs/features/cost-receipts.md`. (#350)

## 1.3.1

Usage
- Live counter charts for a selected local llama.cpp or vLLM runtime on the desktop Usage screen, read through the authenticated `/api/usage/live` route from loopback addresses only; the status line is a screen-reader live region. (#309)

Search and checks
- One library of deterministic checks (schema, AST, state machine, value on page, recompute) with one call and one receipt, used by search as candidate pre-checks and by the pre-action monitor as a layer-0 gate; catches 38 of a 40-item false-accept corpus with 0 false rejects on 353 known-good items. See `docs/features/checks.md`. (#343)

Native provider sessions (preview)
- Persistent, resumable, approval-gated Codex and Claude sessions inside the gateway operation, grant and trace path; desktop `native` chat mode; managed Codex gateway flags; `MODEL_SELECTION_REQUIRED` for `codex-cli` without a model; `--strict-bind`; Tailscale address lookup for the mobile launcher; `state/codex-managed-policy` registered in the trace inventory. (#282)

Integrations
- The Claude Code mod is licensed `FSL-1.1-MIT` with its own LICENSE file; audit fixtures renamed to `forged-consent-sample` and `permissive-policy-sample`. (#341)

## 1.3.0

Pre-action monitor
- Hold model-API requests that ask a provider to fetch a web page, including encoded bodies, script files and provider-side search tools (`egress/003`); hold reads of inference credential files (`credential/001`). (#326)
- Optional rule `scope-escape/004` for side-effecting tool names, off by default; turn on with `monitor.optional_rules`. (#327)
- `flywheel monitor owner` prints `installed_rules_digest`; docs cover re-pinning, single-agent scope and known limits. (#336)

Search and evaluation
- Search mode: the visible tests pick a candidate and the hidden tests decide on it; runs without hidden tests are labeled self-scored. `best_of_k` needs a held-out scorer or `self_scored=True`. (#328)
- Opt-in duplicate pruning, `--prune-duplicates M`. (#332)
- Held-out rerun of the shipped hard benchmark. (#337)
- Report-only red check on pull requests. (#324)
- Read-only evaluation result admission guard for offline evaluation consumers. (#311)

Re-derivation and receipts
- Replay certificate for seeded solvers. (#329)
- `flywheel rederive`, a re-derivation gate with a standard-error luck margin (preview). (#333)
- Routed receipts: which lane produced a result, bound into a signed digest. (#331)
- Findings report scores between a trivial baseline and a ceiling. (#330)

Scoring
- Honest exit outcome with an `exit_price` setting, default 0. (#334)

Integrations
- Claude Code mod under `integrations/claude-code-mod/`, experimental. (#335)
- The mod runs on Claude Code 2.1.286 and installs from the Flywheel plugin marketplace as `flywheel-mod@flywheel-skills`; the wheel now ships the monitor's rule pack `harness/preaction/rules_v1.json`. (#339)

Canon
- Rules of record under `docs/rules/`: evidence and useful work, evaluation that informs decisions, neutral evaluation, compete to win, environment attribution and voice, just culture, the commons, threat-informed defense, coordinated disclosure, conflict transparency and research synthesis; credo additions. (#338)

Gateway
- Static serving rejects hidden paths and unsupported file types and resolves directory indexes before the containment check; malformed chat `temperature`, `max_tokens` and `seed` return a structured 400. (#310)
