# Forum (Flywheel orchestration lane)

> Integration status: native lane. Forum is registered in the Flywheel lane
> registry, carries a desktop destination card, is pinned by an expected-set
> test, and ships an interop payload manifest. The claims below are grounded in
> the forum repo (`public/forum`) and the Flywheel repo (`public/flywheel`).

## Description

**One sentence.** Forum is Flywheel's orchestration lane: it routes a plain
request to a lane without a model, plans it into parallel waves, runs it across
model-agnostic executors under bounded budgets, and writes every routing
decision, task, result, and verdict into a hash-chained, content-addressed
ledger you can verify, replay, and challenge.

**One paragraph.** Inside Flywheel, Forum is the `orchestration` organ. It takes
a request (from the desktop app, the gateway, another lane, or the `forum` CLI),
decides a route from a fixed 28-route roster with no model call, and attaches a
`forum.route-frame/v1` frame carrying domain, intent, posture, delivery profile,
runtime tier, and an embedded communication contract. It plans a dependency
graph into waves, runs those waves across executors that can be a shell command,
any OpenAI-compatible chat endpoint, or the Anthropic API, and caps each run by
model calls and wall clock. Each run appends to a causal ledger built from two
primitives: a hash chain (every entry fingerprints the one before it) and
content addressing (bodies stored under a fingerprint of their own bytes). A
shallow `verify()` checks that the chain links; `verify(deep=True)` re-hashes
each stored body and catches a tampered payload even when the chain still links.
The engine composes with peers through two default-off seams: a `ContextProvider`
feeds organized context in before a run, and a `VerifierProvider` checks the
answer after. Both default to no-ops, so Forum stands alone and stays a real
lane whether or not its peers are installed.

## Feature list (code-bound)

Each item names the module in the forum repo that implements it.

- **Deterministic routing with a human contract.** `forum route` decides a route
  from a fixed roster with no model call and attaches a route frame (domain,
  intent, posture, delivery profile, runtime tier, communication contract).
  `src/forum/routing.py`, `src/forum/route_frame.py`,
  `src/forum/communication_contract.py`.
- **Wave planning.** A request is planned into a dependency graph and executed in
  parallel waves. `src/forum/plan.py`, `src/forum/engine.py`,
  `src/forum/dispatch.py`.
- **Three model backends behind one command.** A shell command (`--cmd`), any
  OpenAI-compatible server (`--chat-url`), or the Anthropic API (`--api`).
  `src/forum/executor.py`, `src/forum/chat_executor.py`,
  `src/forum/api_executor.py`.
- **Tiered executors.** Route agents to cheap, capable, and frontier executors by
  roster tier, set per tier or loaded from a TOML runtime config.
  `src/forum/roster.py`, `src/forum/runtime_config.py`,
  `src/forum/runtime_descriptor.py`.
- **Witnessed escalation.** Every result records the model that produced it; a
  failed task escalates up a ladder of stronger executors on an auditable
  verdict. `src/forum/engine.py`, `src/forum/control.py`.
- **Bounded budgets.** `RunBudget` caps a run by model calls and wall clock;
  `ContextBudget` admits, trims, or omits request context, per-task context,
  upstream injection, and synthesis inputs under approximate-token caps.
  `src/forum/budget.py`, `src/forum/context_budget.py`.
- **Context preflight.** Estimate context pressure before spending a model call,
  and read a peer context envelope if one is supplied.
  `src/forum/context_preflight.py`.
- **Delivery quality checks.** A deterministic concision floor flags verbose
  answers; an opt-in reviser tightens them and is accepted only if the shorter
  answer still covers the request. Expert delivery profiles (`operator`,
  `engineer`, `researcher`, `executive`) check the final answer against a local
  prose contract selected from the route. `src/forum/delivery.py`,
  `src/forum/delivery_profile.py`, `src/forum/humanize.py`.
- **Human-in-the-loop gates.** Pause a run at a wave boundary until you approve,
  edit, or reject it; gates carry durable deadlines with a witnessed
  auto-decision on expiry. `src/forum/gates.py`.
- **Crash-safe resume.** Runs checkpoint at wave boundaries and resume from the
  durable ledger, reusing every task already witnessed as successful.
  `src/forum/engine.py`, `src/forum/storage.py`.
- **Verifiable causal ledger.** Hash chain plus content addressing;
  `verify(deep=False)` checks chain links, `verify(deep=True)` re-hashes present
  bodies, `replay(until=...)` rebuilds past state, `causal_chain(seq)` follows
  parent links, `checkpoint()` folds history into one Merkle root built to avoid
  the second-preimage issue CVE-2012-2459. `src/forum/ledger.py`.
- **Durable storage modes.** In-memory by default; `FileStorage` appends each
  entry to a JSONL file and fsyncs before the next, tolerating a crash-torn final
  write; a SQLite backend is also available. `src/forum/storage.py`,
  `src/forum/sqlite_storage.py`.
- **Run rooms and capsules.** Project the latest run into a readable brief with
  state, risk, and deterministic next actions; compact a run into a reusable
  context brief for the next one. `src/forum/run_room.py`,
  `src/forum/run_brief.py`, `src/forum/context_capsule.py`.
- **Campaigns.** Declare a multi-project campaign as a JSON feature graph and
  drive it to a fixed point; cycles are caught up front.
  `src/forum/campaign.py`, `src/forum/campaign_dispatch.py`,
  `src/forum/campaign_status.py`, `src/forum/campaign_ingest.py`,
  `src/forum/campaign_room.py`.
- **Flight recorder.** Normalize an external agent trace (LangSmith, OTel,
  AgentOps shape) into a verifiable ledger. `src/forum/flight_recorder.py`.
- **Action receipts and flagship envelope.** Emit a submit action receipt and a
  flagship-action status envelope for peers and the gateway.
  `src/forum/receipts.py`, `src/forum/flagship.py`.
- **Always-on surfaces.** One asyncio daemon serves the engine over HTTP;
  `forum mcp` exposes the same tools over MCP stdio as a thin adapter over the
  HTTP surface, so the two cannot drift. `src/forum/daemon.py`,
  `src/forum/http_surface.py`, `src/forum/mcp_surface.py`.
- **Deep-verify benchmark.** `forum bench-deep-verify` times chain-only verify,
  payload-only verify, and full deep verify separately across entry count,
  payload bytes, storage mode, and redaction ratio, emitting a
  `forum.deep-verify-benchmark/v1` receipt. `src/forum/bench_deep_verify.py`.
- **Zero runtime dependencies.** `dependencies = []` in the package manifest;
  Python 3.11+. `pyproject.toml`.
- **Two composition seams, default off.** `ContextProvider` (feeds context in)
  and `VerifierProvider` (checks the answer), both defaulting to no-op so the
  lane runs standalone. `src/forum/context.py`, `src/forum/verify.py`,
  `src/forum/engine.py`.

## Stepwise usage (how a user runs it)

### Path A: over the `forum` CLI directly

The lane is the `forum-engine` package; the command is `forum`.

```bash
pip install forum-engine
```

Route with no model:

```bash
forum route "build the auth endpoint and the database schema"
```

Run a request against a local model, then read and verify the record:

```bash
forum submit "ship a login API" --cmd "ollama run llama3"
forum ledger show --limit 20
forum ledger verify
forum ledger room --brief
```

Run the always-on surfaces:

```bash
forum serve --chat-url http://localhost:11434/v1/chat/completions --model llama3
forum mcp --cmd "ollama run llama3"
```

`forum --help` lists the surface: `status`, `doctor`, `demo`, `humanize`,
`route`, `submit`, `serve`, `mcp`, `context`, `runtime`, `ledger`, `gate`,
`campaign`, `bench`, `bench-deep-verify`. From a source checkout the same CLI is
`python -m forum`.

### Path B: as a Flywheel lane (native)

Forum is a registered lane, so the Flywheel harness resolves and launches it for
you.

1. Check lane health from the harness: `python -m harness.lanes` prints the
   roster; Forum shows as `live`, `declared`, or `missing` from its install and
   runtime selection (`harness/lanes.py`).
2. The gateway spawns the lane on demand and forwards read requests to it (see
   Composition below). No manual launch is needed.
3. In the desktop app, open the **Forum** destination (abbreviation `FM`, in the
   Advanced group) to read the lane's action envelope, ledger checkpoint, pending
   approval gates, and current run room.

## Piecewise reference (each capability, what it does)

### CLI surface (`src/forum/cli.py`)

| Command | What it does |
| - | - |
| `forum route` | Decide a route and print the route frame. No model call. |
| `forum submit` | Plan and run a request across executors; append to the ledger. |
| `forum plan` | Plan a request into a dependency graph of waves without running. |
| `forum ledger show / verify / room / capsule` | Read the record, verify the chain (and deep bodies), project a run room brief, or compact a run into a capsule. |
| `forum gate list / approve / edit / reject` | Manage human-in-the-loop approval gates. |
| `forum runtime inspect` | Explain the merged runtime policy before a run. |
| `forum context preflight` | Estimate context pressure before spending a call. |
| `forum campaign declare / status / next / run / ingest-status` | Drive a multi-project feature graph to a fixed point. |
| `forum humanize` | Apply the prose delivery pass to text. |
| `forum serve` / `forum mcp` | Start the HTTP daemon or the MCP stdio adapter. |
| `forum status` / `forum doctor` | Report the lane's action envelope and health. |
| `forum bench` / `forum bench-deep-verify` | Run benchmarks, including the deep-verify scaling receipt. |

### MCP tools (`src/forum/mcp_surface.py`)

The MCP names and the internal handlers they map to:

- `forum.submit` → submit
- `forum.route` → route
- `forum.plan` → plan
- `forum.prose.humanize` → humanize
- `forum.prose.contract` → prose_contract
- `forum.status` → flagship_status
- `forum.doctor` → flagship_doctor
- `forum.verify` → verify
- `forum.ledger.get` / `forum.ledger.summary` / `forum.ledger.capsule`
- `forum.run.room`
- `forum.runtime.inspect`
- `forum.context.preflight`
- `forum.gate.list` / `forum.gate.approve` / `forum.gate.edit` / `forum.gate.reject`

The MCP server is a thin adapter over the HTTP surface, so the two surfaces
expose the same behavior.

### Ledger primitives (`src/forum/ledger.py`)

- `verify(deep=False)` returns True only if the hash chain links.
- `verify(deep=True)` also calls `verify_payloads()` to re-hash each
  present body; a tampered body returns False even when the chain still links.
- `replay(until=seq)` rebuilds the exact state at a past point.
- `causal_chain(seq)` follows parent links to answer why an entry exists.
- `checkpoint()` folds the history into one Merkle root, guarded against the
  CVE-2012-2459 second-preimage collision.

### Storage backends (`src/forum/storage.py`, `src/forum/sqlite_storage.py`)

- In-memory (default).
- `FileStorage`: append-and-fsync JSONL, survives a restart and a crash-torn
  final write, still verifies exactly.
- SQLite backend for a queryable store.

## Composition tutorial (how Forum plugs into the application)

### Which lane and seam it is

Forum is the `orchestration` organ in the Flywheel lane registry. Registry entry
(`harness/lanes_registry.py`):

```python
"forum": Lane(
    "forum", "forum-engine", "forum", ("mcp",), "pip", "1.13.0",
    "witnessed causal ledger + model-agnostic routing",
    "orchestration", source_repo="public/forum", py_module="forum.cli"),
```

`install_name` is `forum-engine`, the command is `forum`, the MCP args are
`("mcp",)`, the kind is `pip`, and it is version-pinned to `1.13.0`, which
matches the package manifest. Forum is also part of the harness `SPINE` tuple in
`harness/gateway.py`.

### What it consumes from peers

From the interop payload manifest (`forum.interop.json`):

- **`external-agent-trace/1`** via `src/forum/flight_recorder.py:normalize_trace`.
  A LangSmith, OTel, or AgentOps trace is normalized, then imported into a
  verifiable ledger.
- **`project-telos.context-envelope/v1`** via
  `src/forum/context_preflight.py:_index_context_envelope_summary`. Forum reads a
  bounded context envelope produced by the `index` lane (the `structure` organ)
  and folds it into its preflight; the code checks
  `data.get("schema") == "project-telos.context-envelope/v1"` before trusting it.
- Through the engine seams, organized context arrives on the `ContextProvider`
  seam (the `index` lane fills it) and answer checks arrive on the
  `VerifierProvider` seam (the `crucible` lane, the `verification` organ, can
  fill it). Both default to no-op, so a missing peer degrades to standalone,
  not to a crash.

### What it emits for peers

Also from the interop manifest:

- **`project-telos.flagship-action/v1`** (`src/forum/flagship.py:envelope`): the
  action envelope the gateway and desktop read for lane status.
- **`project-telos.action-receipt/v1`** (`src/forum/receipts.py:submit_receipt`):
  a submit action receipt.
- **`forum.flight-recorder/1`** (`src/forum/flight_recorder.py:import_trace`): a
  trace imported into a verifiable ledger.
- **`forum.context-capsule/v1`**
  (`src/forum/context_capsule.py:build_context_capsule`): a witnessed context
  capsule for the next run.

### How the application reaches it

The gateway spawns the lane and forwards read requests through a degrading proxy
(`harness/gateway_lane_calls.py:_forum_mcp_call`), which resolves the launch with
`resolve_mcp_launch("forum")` and returns an honest error dict if the lane is
down. The gateway HTTP routes (`harness/gateway.py`) are:

- `GET /api/forum/status` → `forum.status`
- `GET /api/forum/ledger` → `forum.ledger.summary`
- `GET /api/forum/gates` → `gate_list`
- `GET /api/forum/run-room` → `forum.run.room`

The desktop client wraps those routes in `desktop/lib/client/gateway_forum.dart`
(`forumStatus`, `forumLedger`, `forumGates`, `forumRoom`), typed by
`desktop/lib/models/forum_models.dart` and rendered by
`desktop/lib/views/forum_view.dart`. The destination card lives in
`desktop/lib/navigation/destination_catalog.dart`
(`DestinationSpec(DestinationId.forum, 'Forum', abbr: 'FM', group: DestinationGroup.advanced)`).

### Worked example: index feeds Forum, Forum records the run

1. The `index` lane builds a bounded context envelope for a request and stamps it
   `project-telos.context-envelope/v1`.
2. That envelope is handed to Forum as the request context. `forum context
   preflight` reads it through `_index_context_envelope_summary`, confirms the
   schema, and reports how much of the token budget the context will use before
   any model call is spent.
3. `forum submit` routes the request, plans it into waves, and runs it under a
   `RunBudget`, appending each routing decision, task, result, and verdict to the
   ledger. If a `crucible` `VerifierProvider` is wired, its verdict on the final
   answer is witnessed as one more ledger entry; if it is not wired, the run is
   still complete and the verdict entry is simply absent.
4. `forum ledger verify` links the chain; `forum ledger verify --deep` re-hashes
   the bodies. The gateway exposes the same run to the desktop **Forum** view
   through `/api/forum/ledger` and `/api/forum/run-room`, so an operator reads the
   checkpoint and the run brief without leaving the app.

### How this native wiring was established

Forum was made native the same way the lane layer expects any lane to be, and
each piece is present and testable:

- **Lane registry entry**: `harness/lanes_registry.py` (`LANES["forum"]`).
- **Expected-set test**: `tests/test_lanes.py::test_registry_covers_the_expected_lanes`
  pins Forum into the required lane set, and
  `test_install_name_to_command_asymmetry_is_mapped` asserts
  `install_name == "forum-engine"` and `command == "forum"`.
- **Desktop app card**: the `DestinationId.forum` spec plus the view, models, and
  client under `desktop/lib`.
- **Payload manifest**: `forum.interop.json`, declaring the `emits`, `consumes`,
  and `evidence` files above.
- **Gateway seam**: `_forum_mcp_call` and the four `/api/forum/*` routes.
- A route-receipt harness check exists at
  `tests/test_forum_route_receipts.py` (schema `harness.forum-route-receipts/v1`),
  which records route metadata without calling the model.

## Honest nulls and bounds

- Forum is installable from PyPI as `forum-engine` and carries no
  `package_disabled_reason` in the registry, unlike some sibling lanes that
  require a source checkout. Observed, from `harness/lanes_registry.py`.
- The registry version (`1.13.0`) and the package manifest version (`1.13.0`)
  are aligned at the time of reading. A future package bump that skips the
  registry would drift; the version is a hand-maintained constant, not derived.
- The gateway HTTP surface proxies only four read-only forum endpoints. The
  write-path and preflight tools (`forum.submit`, `forum.route`, `forum.plan`,
  `forum.gate.approve/edit/reject`, `forum.context.preflight`,
  `forum.runtime.inspect`) are reachable over the lane's own MCP and HTTP
  surfaces but are not yet forwarded through the gateway origin. This is an
  observed depth gap. The tools are registered; only the gateway forwarding is
  missing. See the integration gap note.
- The `ContextProvider` and `VerifierProvider` seams default to no-op. Peer
  composition with `index` and `crucible` is a supported seam that stays off by
  default. If no peer is wired, Forum records the run without external context
  injection or an external verdict, and says so by the absence of those entries.
- Version, tool, endpoint, and path facts here are high confidence (read from
  source). The behavioral summaries of routing and delivery are drawn from the
  module docstrings and the README, which are code-adjacent but were not
  re-executed for this document.