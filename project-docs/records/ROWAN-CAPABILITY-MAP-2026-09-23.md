# Rowan capability map, 2026-09-23

This record says what Rowan, the desktop agent, ships on `main` at `91dfd406d`
for each capability in the 2026-09-23 competitive recon matrix. It decides what
gets built next. Every row was checked in code, not only in docs. Where a doc
says more than the code does, the row says so.

Rowan here means the `agent.run` operation the desktop starts from the Rowan
card (`desktop/lib/controllers/rowan_operation_controller*.dart`,
`desktop/lib/widgets/rowan_operation_card.dart`), executed by the gateway
worker in `harness/gateway_agent_execution.py:run_private_agent`. That function
runs one of three paths: the text tool loop (`harness/router_agent.py` over
`harness/local_loop.py`), the provider-native tool loop
(`harness/gateway_agent_native_tools.py`, `harness/gateway_agent_native_runtime.py`),
or a native CLI session (`harness/gateway_cli_execution.py`).

Competitor facts come from a third-party recon and are not repeated here. Only
the capability names are used.

## Headline

23 capabilities mapped: **6 shipped, 13 partial, 4 absent.** Pricing is listed
as a fact and not counted.

The recon's own Rowan row overstates two things this repo does not back:
"rollback shipped in the actuation core" and "read-only computer-use core
shipped". Neither is reachable from a Rowan run on `main`. See rows 4 and 12.

## Matrix

| # | Capability | Status | Ships today | Partial or absent |
|---|---|---|---|---|
| 1 | Plain-words task to a recorded run | Shipped | `agent.run` from the Rowan card; approval sheet, worker process, private hash-chained trace (`harness/gateway_agent_trace.py`) | The agent worker starts only on Windows: `harness/cross_harness_process.py:start_owned_process` raises on Linux and macOS |
| 2 | Surfaces | Partial | Windows desktop app and installer (`desktop-release.yml`); `flywheel` CLI; stdio MCP servers | Android builds locally only; macOS and Linux folders exist with no build job; the browser shell is labelled a dev fallback in `harness/gateway.py`; no iOS, no hosted version |
| 3 | Autonomy and approval | Partial | One exact grant per run, single use, bound to the operation digest and Journey head (`harness/operation_grants.py`); write and exec off by default; stop needs its own grant | No per-action approval; once approved, every tool call runs to the step limit with no further prompt |
| 4 | Computer use | Partial | User-controlled screen sharing (`harness/live_screen_sources.py`, `desktop/lib/controllers/live_screen_controller.dart`), one granted frame delivery per call (`harness/live_screen_provider_delivery.py`) | Not a Rowan tool: the agent loop never sees the screen; capture needs an external package; window capture is not implemented; no click, type or accessibility-tree reading anywhere in the repo |
| 5 | Browser use | Partial | Gate and hash-chained record for browser actions (`harness/browser_control.py`, `harness/browser_route.py`); an opt-in driver that does read and same-site navigate (`harness/telos_browser_bridge.mjs`) | Not in Rowan's tool set; click, type, screenshot and download are gated but no driver performs them; the POST route needs only the bearer token |
| 6 | Memory and personalization | Partial | Local chat history (`desktop/lib/services/chat_store.dart`); opt-in Canon context retrieval labelled untrusted (`desktop/lib/models/context_memory.dart`) | No memory the user can view or edit; Canon setup is environment variables only and Canon is not a declared dependency |
| 7 | Voice | Partial | Speech in and out on Android (`desktop/lib/shell/flywheel_shell.dart` picks it only on mobile); opt-in prerecorded cue clips on desktop | No speech-to-text or spoken replies on desktop; `desktop/lib/assistant/local_tts_voice.dart` is not wired |
| 8 | Model choice | Shipped | 36 roster endpoints (`harness/endpoint_registry.py:unified_roster`): 30 OpenAI-compatible specs in `harness/providers.py` including 8 local servers, plus anthropic, gemini and CLI profiles | Provider-native tool calling only for OpenAI at api.openai.com and Anthropic; native CLI mode in the UI allows only `claude-cli` |
| 9 | Local and offline | Shipped | Gateway on 127.0.0.1 with a bearer token; local endpoints (ollama, vllm, llama.cpp and others) run with no network | Same Windows-only worker limit as row 1 |
| 10 | Data use and telemetry | Shipped | No analytics or crash-reporting SDK found in `harness/`, `desktop/lib` or `site/`; keys in the Windows credential store, reported as presence only (`harness/keychain.py`, `harness/credential_handles.py`) | Keychain storage is Windows only; chat history is plain JSON on disk; `desktop/CLAUDE.md` says the app never collects keys, but `desktop/lib/widgets/keys_panel.dart` takes a key value and posts it to the keychain route |
| 11 | Audit trail and receipts | Shipped | Every run: private trace chain, session ledger, run verdict (`harness/run_verdict.py`), HMAC-signed tool results, action witness chain, content-free effect evidence on the terminal projection (`harness/gateway_effect_evidence.py`), offline verifier (`harness/gateway_effect_offline.py`) | Receipts prove what was recorded, not semantic truth; each block carries its own `does_not_prove` |
| 12 | Undo and rollback | Absent | Workspace hashes before and after a run (`harness/router_agent.py:_workspace_pre/_workspace_post`); per-edit post-write hashes; `apply_patch` is all or nothing | Nothing restores a file after an agent edit. `harness/workspace_state.py` describes "revert with proof", but no revert code exists. Continuation "undo" writes a ledger record and touches no file |
| 13 | Run budget circuit breaker | Partial | `max_steps` (1 to 12) caps model calls; `max_tokens` caps each call; `timeout_s` is one aggregate deadline over the worker tree (`harness/gateway_agent_deadline.py`); provider non-2xx fails the run | No cap on total tokens, spend or tool actions (the text loop can run many tool calls per step); no detection of a step that exits 0 while its output reports a rate limit, quota or auth error; the CLI path accepts a `success` result whatever its text says (`harness/gateway_cli_events.py`) |
| 14 | Verified versus claimed completion | Partial | Engine pieces exist: the test-repair loop and `tests_pass_trusted` (`harness/local_loop.py`), acceptance criteria, `run_review` unverified edits (`harness/run_review.py`), the behavioral monitor flagging success claims with no receipt (`harness/behavioral_monitor.py`) | The Rowan operation never sends `test_cmd`; no per-deliverable split of verified, claimed and failed; the card shows no completion verdict, and a completed run reads the same whether anything was checked or not |
| 15 | Isolation that matches the architecture | Partial | `run` goes through a sandboxed runner: Windows low-integrity token and job object; bubblewrap or Seatbelt elsewhere (`harness/sandboxed_runner.py`); no sandbox means refuse by default (`harness/tool_sandbox_bridge.py:fallback_from_env`) | Reads are not confined; Windows does not restrict network; `harness/posix_sandbox.py` says network is denied by default while the runner allows it unless `FLYWHEEL_EGRESS_HOSTS` is set; file writes have no protected-path list inside the workspace |
| 16 | Prompt-injection defense | Partial | Selected source context is framed as untrusted data with a hashed delimiter (`harness/source_context_worker.py:materialize_goal`); an injection probe measures containment | The canary tripwire exists but no shipped path passes canaries (`harness/gateway_agent_execution.py` does not); tool and MCP output go back to the model with no untrusted label; docs describe the canary as an agent feature |
| 17 | Connectors | Partial | Rowan MCP admission with scopes, hashing and limits; the trusted catalog admits one read-only tool, `index.doctor` (`harness/gateway_agent_mcp_authority.py`); a 17-server plugin marketplace outside Rowan | No credentialed MCP server can reach Rowan (`MCP_CREDENTIAL_VERSION_UNAVAILABLE`); no mail, calendar or chat connectors |
| 18 | Write-class actuation (forms, purchases, accounts) | Absent | None | No code path |
| 19 | Scheduled and recurring runs | Partial | Schedules with hash-chained fire records that name lateness and skipped occurrences (`harness/scheduler.py`, `harness/schedule_route.py`); a fire runs granted hook commands | A schedule cannot start `agent.run`; the tick is a pull and nothing calls it on its own; the desktop has no way to define a schedule (`ScheduleApi.define` has no caller); no budget or breaker, and a hook that exits 0 with a rate-limit message counts as success |
| 20 | Browser-embedded operation | Absent | None | Rowan runs as a desktop app and a gateway, not inside the user's browser |
| 21 | Take a session elsewhere (export) | Absent | Import exists: continuation reads another agent's transcript export and git state (`harness/continuation_preview.py`); journey export writes a JSON custody packet | No export of a Rowan session's goal, decisions, open items and receipts as a brief another agent can read. A cue clip announces a Markdown export that does not exist |
| 22 | Persona that survives a model swap | Partial | Name, welcome text and voice profile are constants independent of the model (`desktop/lib/assistant/assistant_identity.dart`) | No Rowan system prompt is sent, so tone and self-description change with the model (`project-docs/ROWAN-IDENTITY.md` says so) |
| 23 | Honest status on the surface | Shipped | `HonestNull` rendering of errors and nulls; `does_not_prove` on projections, effect evidence and receipts | Captions show the model's final text as written, with no verdict beside it |
| - | Pricing | Fact | Free; `LICENSE` is FSL-1.1-MIT; `flywheel-verify` on PyPI | No paid tier |

## What this decides

Rows 13 and 14 are the two gaps where the engine already holds the evidence and
the user still cannot see or rely on it. They also sit on the failure the recon
names most often: a run or a scheduled job that reads as success while its
output reports a limit, and a run reported finished with nothing checked. Both
are built next, in this order:

1. A run budget circuit breaker on every Rowan run: model calls, tool actions,
   provider-reported tokens, provider-reported cost where a provider reports it,
   and wall time, with defaults and a per-run override. It stops the run at the
   next step boundary, records the reason in the private trace and the terminal
   projection, and shows it on the card. The same limit-signature check marks a
   step failed when it exits 0 while its output reports a rate limit, quota,
   auth or billing error. Scheduled fires get the signature check and a
   consecutive-failure breaker, since a schedule cannot start `agent.run`.
2. A completion report per run that marks each deliverable verified, claimed or
   failed, names the check behind each verdict, and never lets the card say
   "done" when anything rests on the model's word alone.
3. A plain Markdown export of a Rowan session for use in another agent (row 21),
   if time remains after 1 and 2.

Rows 4, 12, 16 and 18 stay open. Row 12 (rollback) is the next candidate after
this slice, because row 1's receipts already record the hashes a restore would
need to check against.

## What this branch changes

The matrix above is `main` before this branch. After it:

| # | Capability | Status | What changed |
|---|---|---|---|
| 13 | Run budget circuit breaker | Shipped | Per-run limits on model calls, tool actions, provider-reported tokens and spend, with the existing wall-time deadline; exit-0 limit errors recorded as failed; stop reason in the trace, the projection and the card (`docs/RUN-BUDGET.md`). Spend applies only where a provider reports cost |
| 14 | Verified versus claimed completion | Shipped | Every run ends with a per-deliverable split rechecked by the gateway against the trace; the card says "Done" only when everything is verified; a check command field makes the final answer verifiable (`docs/VERIFIED-COMPLETION.md`) |
| 19 | Scheduled and recurring runs | Partial | Hook receipts mark exit-0 limit errors as failed, and a schedule stops after two failed fires in a row until redefined. A schedule still cannot start `agent.run` |
| 21 | Take a session elsewhere | Partial | One finished run exports as a provider-neutral Markdown brief (`docs/ROWAN-HANDOFF.md`). A multi-run session export does not exist |

Counts after this branch: 8 shipped, 12 partial, 3 absent (rows 13 and 14 move
from partial to shipped, row 21 from absent to partial).

## Limits of this map

- Checked by reading code on one commit. Nothing here was run against a live
  provider.
- Counts depend on how rows are drawn. A row is Shipped only when the core of
  the capability works end to end from the Rowan card today.
- Docs that disagree with code are listed in rows 10, 12, 15 and 16. They were
  not edited in this change.
