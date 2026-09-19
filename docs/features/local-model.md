# Local-model (Flywheel engine lane)

> Native feature documentation for the local-model lane as it lives inside Flywheel. Every claim below is bound to code in the Flywheel harness (`harness/local_mcp.py` and the modules it imports). Observed facts are stated plainly; anything proposed or in flight is marked. local-model is a bundled lane. It ships with the engine as part of Flywheel (`flywheel-verify`, license FSL-1.1-MIT).

## One sentence

local-model is Flywheel's engine lane: it exposes the on-machine agent that proposes with a local model, runs gated tool work under a hash-chained witnessed ledger, and returns per-turn and per-run receipts a stranger can recompute, so the oracle decides and the model only proposes.

## One paragraph

Inside Flywheel, local-model is the `propose-verify` organ. It is bundled (`kind="bundled"` in `harness/lanes_registry.py`), so nothing installs it and it is never missing: it is Flywheel. The lane is a zero-dependency stdio JSON-RPC 2.0 server (`harness/local_mcp.py`, protocol `2025-06-18`) that any harness can spawn with `python -m harness.local_mcp`. It fronts two local model tiers in preference order, the model served by `harness/serve.py` over localhost (the project's trained coder) and an Ollama model, with health-gated failover between them (`harness/local_agent.py`). A one-shot completion returns a content-addressed receipt that binds request, prompt, model, and response, so an identical turn shares an id and any change breaks the recompute (`harness/messages_api.py`). A gated agentic run drives the model through a text tool protocol a small model can emit, sandboxes reads to a root, keeps writes and command execution off unless the caller allows them, and records every step into a sha256 hash-chained session ledger that re-derives on verify (`harness/local_loop.py`, `harness/local_tools.py`, `harness/local_session.py`). The lane also verifies receipt-log membership as a replayable Merkle proof (`harness/receipt_operations.py`) and bridges to Canon context memory over a bounded child process (`harness/context_memory_bridge.py`). Because it can execute code, Flywheel floors the whole lane at governance tier T2 (`harness/lane_caller.py`). Every verdict it carries ships its own does-not-prove line: a hash chain proves the submitted entries are internally consistent. It does not prove that the recorded actions happened or that the answer is correct.

## Feature list

Each item names the module that implements it.

- **Two local model tiers with health-gated failover.** `available_backends()` in `harness/local_agent.py` returns `ServeBackend` then `OllamaBackend`, in that preference order. `ServeBackend` talks to `harness/serve.py` at `http://127.0.0.1:8765` (POST `/generate`, GET `/health`); `OllamaBackend` talks to Ollama at `http://127.0.0.1:11434` (`/api/chat`, `/api/tags`). A turn tries healthy backends in order and the first that returns a completion wins (`LocalAgent.send`).
- **Local-only by default, hosted tiers opt-in.** The default roster is the two local tiers. Passing `online=true` extends it with hosted endpoints built by `harness/endpoints.py` (`_backends()` in `harness/local_mcp.py`). The local agent proxies no hosted account and harvests no session token; its local tiers speak only to model servers on localhost (`harness/local_agent.py` module docstring).
- **Largest local Ollama model chosen by tag.** With an empty model name, `OllamaBackend.health()` resolves the biggest installed model by its `NNb` tag through `_prefer_largest` (32b over 14b over 7b), else the first tag.
- **Backend identity is checked, not trusted.** `OllamaBackend.chat` raises `MalformedBackendOutput` when the response model is missing or does not match the requested model; the streaming path enforces the same check on each chunk. The per-turn receipt records a `model_mismatch` when the served model differs from the requested one (`make_receipt` in `harness/messages_api.py`).
- **Routing as an auditable claim.** `select_backend_receipted` emits a `flywheel.routing-receipt/v1` record: every candidate probed, its health verdict, the chosen backend, and the reason. Probing stops at the first healthy backend and unprobed candidates are not invented.
- **Content-addressed per-turn receipt.** `make_receipt` binds request, prompt, model reference, and response into a 20-hex `receipt_id`. An optional weights fingerprint folds into the id preimage, so tampering with it breaks the recompute. `local_agent_chat` returns the id; `serve.py` surfaces it as an `X-Receipt-Id` header.
- **Gated agentic loop with a witnessed ledger.** `run_agent` in `harness/local_loop.py` runs the goal to completion or `max_steps`, parses text tool calls, executes them through the gate, and appends every user turn, assistant turn, tool call, and tool result to a `SessionLedger`. It returns the final answer, step count, ledger checkpoint, and verify verdict.
- **Text tool protocol for small models.** `harness/local_tools.py` exposes `read_file`, `list_dir`, `repo_map`, `grep`, `glob`, `edit_file`, `write_file`, `apply_patch`, and `run`, each called as one `TOOL name {json}` line. A malformed args object is skipped, not executed.
- **Default-deny gate.** `ToolGate` keeps `write_file`, `edit_file`, and `apply_patch` off unless `allow_write`, and `run` off unless `allow_exec`. External MCP tools stay off unless `allow_mcp`. Each blocked call returns a `[gate]` result the ledger records.
- **Destructive-command denylist.** Even with exec allowed, `_DENY` in `harness/local_tools.py` refuses recursive-force deletes however the flags are spelled, `rmdir /s`, `del /`, `format`, `mkfs`, `dd if=`, `shutdown`, `reboot`, a fork bomb, and `curl|sh` or `wget|sh` pipes. The lookaheads scan the argument span so a later `; safe` cannot mask an earlier destructive verb. This is a guardrail against a small model wrecking the tree. It is not a security boundary against a determined operator.
- **Path confinement that follows links.** `_safe_path` resolves a target under the root and returns nothing when it escapes; `_within` re-confines every `rglob` candidate by its real path, so a symlink or junction inside the tree whose target is outside is never read or listed.
- **Strict edits.** `edit_file` requires its `old` text to match exactly once, so an ambiguous or stale edit is refused. `apply_patch` verifies every hunk before writing a byte, and any mismatch refuses the whole patch.
- **Sandboxed execution with an explicit fallback.** `make_sandboxed_runner` (`harness/tool_sandbox_bridge.py`) routes `run` through the Windows low-integrity sandbox. On a host with no sandbox the default is refuse; `FLYWHEEL_ALLOW_UNSANDBOXED=1` runs the command bare and labels the output `[UNVERIFIABLE: sandbox unavailable]`. A machine-wide policy (`harness/machine_policy.py`) can pin the hatch closed and outranks the variable.
- **Hash-chained session ledger.** `SessionLedger` in `harness/local_session.py` chains entries by sha256; `verify()` re-derives the chain, `checkpoint()` returns the head hash, and `save`/`load` use JSONL with no dependencies. Its own bound: the chain shows the submitted entries are internally consistent; it does not authenticate the producer or prove the actions happened, and catching a consistently rewritten history needs a separately retained checkpoint.
- **Per-run signatures and edit fingerprints.** `run_agent` signs each tool result with a per-run HMAC key (`sign_result`). A mutating tool's receipt carries the post-edit sha256 of the target file (`_edit_fingerprint`), so a stranger binds this edit to a specific file state; an unreadable target yields no fingerprint at all.
- **Sealed tool-call receipt chain and byte witness.** When a receipt directory is set, `ToolExecutor` seals one receipt per call over the same argument bytes it witnesses, chained by prev-sha256, with a capability class (builtin-read, builtin-write, builtin-exec, external-mcp, or unknown) and an outcome (COMPLETED, BLOCKED, or ERROR) (`harness/local_tools.py`, `harness/tool_witness.py`).
- **Integrity-gated pass and acceptance verdicts.** `_done` attaches a trajectory integrity report; `tests_pass_trusted` is true only when the tests passed and the trajectory did not tamper with the check, and `accepted_trusted` applies the same rule to acceptance criteria.
- **Test-repair and acceptance-criteria loops.** With a `test_cmd`, `run_agent` runs the tests when the model believes it is done and feeds a failure back until they pass or steps run out. With `criteria`, it refuses to report done while any criterion is failing and witnesses the check as a ledger entry. `max_steps` is the honest backstop: it ends the run without reporting accepted when criteria are unmet.
- **Canary tripwire.** When canaries are configured, a decoy resource surfacing in a tool output is a hard access signal: the loop contains the run and stops on its own detection, without waiting for the model to have stopped (`harness/canary_tripwire.py`).
- **Bounded external MCP calls.** A registered external tool runs on a daemon thread bounded to 120 seconds; a hang is named as its own witnessed failure and an external tool may not shadow a gated builtin (`ToolExecutor._execute_inner`).
- **Receipt-log inclusion proofs.** `receipt.verify_inclusion` (`harness/receipt_operations.py`) verifies that a 64-hex envelope digest is a member of the ordered receipts Merkle log and returns replayable proof; it does not approve, mutate, or judge receipt semantics.
- **Canon context memory bridge.** `flywheel.context.health`, `flywheel.context.capture`, and `flywheel.context.preflight` bridge to a configured Canon context MCP over a bounded child process (`harness/context_memory_bridge.py`). Unconfigured, it returns a typed 503; `not_found_in_searched_sources` is kept as a real status, never read as evidence a topic was never discussed.
- **Network-free status and doctor.** `local-model.status` reports liveness and identity; `local-model.doctor` adds the tiers the lane would try and the tools it exposes, and reports reachability as `unprobed` because it measured none. `local_agent_health` is the tool that pings a tier.
- **Packaged public skill resources.** `resources/list` and `resources/read` serve a closed manifest of public skill files (`harness/skill_resources.py`); URIs are identifiers, not paths, so traversal and `file://` input never reach the filesystem.
- **Zero runtime dependencies.** `pyproject.toml` declares an empty `dependencies` list; the lane is standard library on Python 3.11 or newer.

## Stepwise usage (how a user runs it)

**As a standalone MCP server.** local-model is bundled, so there is no install step; you run it from the Flywheel checkout.

1. Start a local model tier. Either run `harness/serve.py` (the trained coder tier at `http://127.0.0.1:8765`) or start Ollama with at least one model pulled (`http://127.0.0.1:11434`). With neither live, health tools report no live tier and a run raises "no local backend is healthy".
2. Launch the lane: `python -m harness.local_mcp`. It speaks JSON-RPC 2.0 over stdio.
3. Check what is live: call `local_agent_health`. Add `{"online": true}` to include hosted endpoints in the report.
4. Get a completion: call `local_agent_chat` with `{"prompt": "..."}`. The result carries the text, the backend that answered, and the per-turn `receipt` id.
5. Run a gated task: call `local_agent_run` with `{"goal": "...", "root": "."}`. Reads are sandboxed to `root`; add `{"allow_write": true}` and `{"allow_exec": true}` to enable edits and commands. The result carries the final answer, the step count, the `verified` chain verdict, and the ledger `checkpoint`.

**As a Flywheel lane.** Flywheel launches the server for you; a user does not spawn it by hand.

1. No install. `install_lane("local-model")` in `harness/lanes.py` returns installed with detail "bundled lane (no install needed)".
2. Check health. `lane_status("local-model", probe=False)` reports `declared` (it is always present); `probe=True` spawns the server and calls `local-model.status`.
3. Call a tool. Flywheel routes through `call_lane_tool("local-model", "local_agent_run", args)` in `harness/lane_caller.py`. When a governance tier is supplied it must be at least T2, because the lane can execute code.
4. Read results in the desktop app. The `local-model` lane card (`desktop/lib/models/lane_identity.dart`) titles it "Local model" and renders the training and benchmark receipts surface.

## Piecewise reference (each capability, what it does)

### MCP tools (`harness/local_mcp.py`, `TOOLS`)

| Tool | What it does |
| - | - |
| `local_agent_health` | Report which model tiers are live; `online=true` adds hosted providers. Returns `any_live` and a per-tier list with a healthy flag and a detail string. |
| `local_agent_chat` | One-shot completion from the first healthy tier. Returns the text, the backend name, and the per-turn receipt id. `backend` forces one tier (still health-gated). |
| `local_agent_run` | Run a gated agentic task. Tools are sandboxed to `root`; write and exec are off unless `allow_write` / `allow_exec`. Returns `final`, `steps`, `verified`, and `checkpoint`. `max_steps` defaults to 6. |
| `local-model.status` | Liveness and identity (name, version, protocol). Network-free; a fast probe that does not ping a tier. |
| `local-model.doctor` | Identity plus the tiers the lane would try and the tools it exposes. Network-free, so reachability is reported as `unprobed`. |
| `flywheel.context.health` | Status of the Canon context bridge: scope configuration, owner binding, and the Canon child health, with the current limits kept visible. |
| `flywheel.context.capture` | Ingest one context event into the configured Canon store under the caller's owner and project scope. |
| `flywheel.context.preflight` | Query the Canon store for prior context; returns hits, pending extraction, the sources searched, and a does-not-prove list. |
| `receipt.verify_inclusion` | Verify a 64-hex receipt envelope digest is a member of the receipts Merkle log; returns a replayable proof and a does-not-prove line. |

The server also answers `resources/list` and `resources/read` for the packaged public skill resources.

### Backends (`harness/local_agent.py`)

- `ServeBackend`: the model served by `harness/serve.py` over `/generate`, health via `/health`, default `http://127.0.0.1:8765`, 300 second timeout. When the server returns a `prompt_hash` the receipt uses it; otherwise the receipt hashes the prompt.
- `OllamaBackend`: native `/api/chat`. An empty model selects the largest installed model; `num_ctx` is explicit and omission leaves the server setting unstated. It validates the response model identity and supports an NDJSON streaming path.
- `LocalAgent`: the multi-turn agent, with failover across healthy backends, a per-turn receipt on each completion, opt-in context compaction (`compact_budget`, off at 0), and opt-in recall of folded context through a `fold_index`.
- `health_report`: the "can I keep working offline" check, reporting `any_live` plus a per-tier healthy flag and detail.

### Agentic loop and tools (`harness/local_loop.py`, `harness/local_tools.py`)

| Tool line | What it does |
| - | - |
| `TOOL repo_map {"path": "."}` | A repository map under a sandboxed subpath. |
| `TOOL read_file {"path": "...", "offset": 0}` | Read a file confined to the root. |
| `TOOL list_dir {"path": "..."}` | List a directory confined to the root. |
| `TOOL grep {"pattern": "...", "path": "...", "glob": "*.py"}` | Regex search, link-confined, capped at 200 matches. |
| `TOOL glob {"pattern": "**/*.py"}` | List matching paths, link-confined, capped at 500. |
| `TOOL edit_file {"path": "...", "old": "...", "new": "..."}` | Exact-once search and replace; ambiguous or stale edits refused. |
| `TOOL write_file {"path": "...", "content": "..."}` | Write a file (needs `allow_write`). |
| `TOOL apply_patch {"patch": "<unified diff>"}` | Apply a diff strictly; any hunk mismatch refuses the whole patch (needs `allow_write`). |
| `TOOL run {"cmd": "..."}` | Run a command (needs `allow_exec`, then passes the denylist and the sandbox). |

`run_agent` optional inputs: `test_cmd` (test-repair loop), `criteria` (acceptance-criteria refusal), `sign_key` (per-run HMAC over results), `canaries` (decoy tripwire), `budget_note` (a remaining-step line), and `on_event` (progress stream). The result always carries `checkpoint`, `verified`, an integrity report, a run review, a context manifest, a risk review, and the runtime environment; `tests_pass_trusted` and `accepted_trusted` appear only when the relevant check ran and the trajectory was clean.

### Receipts and verification

- Per-turn receipt (`harness/messages_api.py`): `receipt_id`, `request_hash`, `response_hash`, `prompt_hash`, `model_ref`, `seed`, and a `model_mismatch` block when the served model differs from the requested one.
- Routing receipt (`harness/local_agent.py`): `flywheel.routing-receipt/v1`, the probed candidates and the chosen backend.
- Ledger checkpoint (`harness/local_session.py`): the sha256 head over the chain, re-derived by `verify()`.
- Merkle inclusion proof (`harness/receipt_operations.py`): `flywheel.receipts-proof/v2`, the leaf, index, tree size, root, and audit path, replayed by `harness.transparency_log.verify_inclusion`.

## Composition tutorial (how it plugs into Flywheel)

### Which seam it is

local-model is registered in `harness/lanes_registry.py`:

```python
"local-model": Lane(
    "local-model", "", "python", ("-m", "harness.local_mcp"), "bundled", "0.1.0",
    "the trained 14B proposer + verified-inference harness (the engine lane)",
    "propose-verify"),
```

Organ `propose-verify`, role the propose-then-verify engine. It launches with argv `["python", "-m", "harness.local_mcp"]` (`resolve_mcp_command("local-model")`, pinned by `tests/test_lanes.py::test_public_commands_are_portable_declared_argv`). Because it is bundled, `install_lane` is a no-op and `lane_status(..., probe=False)` reports `declared`, both covered by `tests/test_lanes.py`. Flywheel floors the whole lane at governance tier T2 in `harness/lane_caller.py` (`LANE_MIN_TIERS["local-model"] = "T2"`), alongside `accountable-surface` and `relay`, because it can run code. The lane carries no per-tool tier split, so when a governance tier is supplied every local-model tool needs at least T2, including the network-free status and doctor probes. That is the conservative direction: a gate that widened on its own would not be a gate.

Native wiring is present and tested:

- Lane declaration: `harness/lanes_registry.py` (above).
- Registry membership and bundled behavior: `tests/test_lanes.py` covers the expected-lane set, the portable argv, the declared-not-missing status, and the install no-op.
- Desktop card: `desktop/lib/models/lane_identity.dart` key `local-model`, title "Local model", surface "training and benchmark receipts".
- Call path: `harness/lane_caller.py::call_lane_tool` routes a tool call to the lane and applies the tier gate.

### What it consumes from peers

- Local model completions from `harness/serve.py` and Ollama over localhost. These are the two default tiers.
- Hosted completions from `harness/endpoints.py`, only when a caller passes `online=true`.
- Canon context memory through the configured Canon context MCP, read by `flywheel.context.preflight` and written by `flywheel.context.capture` (`harness/context_memory_bridge.py`). Workspace and project scope come from Flywheel configuration. The request body does not carry them.
- The receipts Merkle log through `gateway.receipts_ledger`, read by `receipt.verify_inclusion`.

### What it emits for peers

- A per-turn receipt (`x_receipt`, `receipt_id`) on every completion, which a peer recomputes from the request and response.
- A witnessed `SessionLedger` on every run: the checkpoint head hash, the `verified` verdict, an integrity report, and, when the checks ran cleanly, `tests_pass_trusted` and `accepted_trusted`.
- Sealed tool-call receipts (`harness/tool_witness.py`) that land in the receipts ledger `receipt.verify_inclusion` and sibling lanes re-derive.
- A routing receipt for the backend it selected.

Because these are data contracts, a peer consumes them without reaching into the lane. A verifier holding a receipt or a ledger checkpoint re-runs the check and gets the same answer; a tampered entry is caught by re-hashing.

### Worked example: local-model proposes, Crucible decides

A two-lane composition that matches the lane's own rule, "the oracle decides, the model proposes".

1. **local-model** runs a gated task: `local_agent_run` with a goal, `allow_write=true`, `allow_exec=true`, and a `test_cmd`. The loop edits code, runs the tests, and feeds failures back until they pass or `max_steps` is reached. It returns the final answer, the ledger `checkpoint`, `verified`, and `tests_pass_trusted`. Each mutating tool call carries the post-edit file sha256 and a sealed receipt.
2. **Crucible** (organ `verification`) registers a falsifiable claim about the same work, for example "the proof or test oracle accepts this change". A `ProofMeasure` or `SubprocessMeasure` runs the checker and produces a deviation at the seam.
3. Crucible's `verdict_for` turns that measurement into MATCH, DRIFT, or UNVERIFIABLE with no model in the step. The model that proposed the change is nowhere in the verdict.
4. The tie-back is a receipt check: hand a sealed tool-call receipt digest to `receipt.verify_inclusion` and confirm it is a member of the receipts Merkle log, or re-derive the ledger checkpoint with `SessionLedger.verify`. A tampered edit or a rewritten step is caught.

The bundle attests that the model proposed this change and these checks reproduce these fingerprints. It does not prove the change is correct in the world. That boundary holds for every composition local-model joins: a receipt proves a check reproduces. It does not prove the answer is right.

A second shape uses the memory seam: before a run, `flywheel.context.preflight` asks Canon what was already decided on this project; after a run, `flywheel.context.capture` records the outcome. The preflight result keeps its does-not-prove line, so an empty search reads as "not found in the sources searched", never as "never discussed".

## Status and bounds

- `flywheel-verify 1.0.1`; the lane server reports `__version__ = "0.1.0"` and protocol `2025-06-18`.
- What this lane observes: which local tiers are live, the completion each returns, the trajectory of a gated run, and whether a receipt or a chain re-derives. What it does not claim: that a hash chain proves an action happened, that a served model is the model requested without the mismatch check, or that a passing test is semantic truth. UNVERIFIABLE and `unprobed` stay visible in the output as their own states.
- Honest null on hosted tiers: the shipped default roster is local-only. The hosted endpoints reached under `online=true` depend on `harness/endpoints.py` configuration and are not part of the offline guarantee.
- local-model is the bundled engine lane. Flywheel composes it as the propose-verify seam and ships it with the engine, so there is no outside package to vendor.