# relay (execution lane)

## One sentence

Relay is Flywheel's execution lane: a zero-dependency, accountable coding agent
that runs on any model endpoint and writes every run to a hash-chained,
re-verifiable session ledger.

## One paragraph

Relay takes a coding goal and drives a permission-checked tool loop against a
model tier it reaches on its own (a served local 14B/32B, Ollama, a subscription
CLI, a provider gateway, or a public API keyed from the environment). It fails
over across those tiers in order, free and private ones first. Writes and shell
execution are off unless you enable them. Every turn, tool call, and result is
appended to a tamper-evident ledger, and a saved run reloads only if its chain
re-derives. Inside Flywheel, relay is a lane declared in
`harness/lanes_registry.py` with organ `execution`; the gateway forwards its MCP
tools so a single phone-facing origin can start a run and get back the same
`run_id` and ledger checkpoint a desktop run gets. Relay is an independent
project (Zentropy Labs); the code lives at `public/relay` and is pulled into
Flywheel as the `relay` git submodule at `relay/src`.

## Feature list

Each item is bound to the source that implements it.

- **Endpoint ladder with failover.** `build_endpoints` and `available_backends`
  (`src/relay/endpoints.py`, `src/relay/local_agent.py`) assemble an ordered set
  of tiers: served local model, Ollama, subscription CLI (`claude`, `codex`),
  public API, provider gateway, and a cloud OpenAI-compatible endpoint. A tier
  whose credential is absent is dropped when the ladder is assembled, so it
  cannot error at call time.
- **Credential handling by construction.** Keys come from environment variables,
  subscriptions from your own authenticated CLI, gateways from a base URL you
  set. A gateway rung uses only its dedicated `<PROVIDER>_PROVIDER_KEY` and never
  falls back to the official API key, so a real credential is not replayed to a
  third-party URL (README "Reaches every endpoint").
- **Gated tool loop.** `run_agent` (`src/relay/local_loop.py`) drives the model
  through `ToolExecutor` and `ToolGate` (`src/relay/local_tools.py`). `write_file`
  is off until `--allow-write`; `run` is off until `--allow-exec`, and
  `allow_exec` implies write.
- **Path-confined file tools.** `read_file`, `list_dir`, `write_file`, and the
  edit tools are confined to `--root`. `run`/exec sets only the working directory
  and is not path-confined, which the tool descriptions state directly
  (`src/relay/local_mcp.py`, `local_agent_run` description).
- **Exact-match and hash-anchored edits.** `edit_file` requires a unique match or
  refuses; `edit_lines` and `edit_plan` (`src/relay/edit_plan.py`,
  `src/relay/hashline.py`) edit by an 8-hex line anchor and fail closed on a
  stale or ambiguous anchor. `apply_diff` (`src/relay/udiff.py`) refuses a hunk
  whose context does not match and leaves the file untouched.
- **Repo map.** `repo_map` (`src/relay/local_repomap.py`) outputs a compact code
  outline (Python via `ast`; several other languages via patterns). `--agent`
  folds a bounded map (stopped at 20 files, capped at 4096 UTF-8 bytes) into the
  system prompt automatically unless `--no-repo-map`.
- **Project conventions.** An `AGENTS.md` or `CONVENTIONS.md` at the root is
  folded verbatim into the system prompt, length-bounded (`src/relay/conventions.py`);
  `--no-conventions` opts out.
- **Hash-chained session ledger.** `SessionLedger` (`src/relay/local_session.py`)
  appends every turn and tool call; `verify()` re-derives the chain on load and
  refuses a broken one (`src/relay/integrity.py`).
- **Per-turn receipts.** Each model turn carries a content-addressed receipt id a
  third party can recompute from the saved record.
- **Interactive approval, witnessed.** `--interactive` (`src/relay/approvals.py`)
  prompts before every mutating call and records each decision as a hash-chained
  ledger entry bound to the call's exact bytes. A headless run is byte-identical
  to one without it.
- **Prompt compaction.** `--compact-budget N` (`src/relay/compaction.py`) folds
  older turns into a summary once the prompt passes N tokens, records the
  folded-span and summary hashes, and keeps the untruncated trajectory on the
  ledger.
- **Acceptance check with your authority.** `--check "<cmd>"` runs your command
  once after the agent finishes, witnesses the result, and accepts the run only
  on pass (`src/relay/local_loop.py:_run_acceptance`). The check runs outside the
  tool permission boundary and is not a call the model can emit. `--test-cmd` is
  the retried variant: on failure the output is fed back to the model until it
  passes or the step budget runs out.
- **Reward-hacking guard.** A non-learned rule set reads the witnessed edit set;
  a green check earned by editing the grading test or injecting `pytest.skip` /
  `sys.exit` is flagged UNTRUSTED and the run is not accepted
  (`src/relay/intent_audit.py`). The guard only ever turns an accept into a
  refusal.
- **Claim grounding.** The final answer is checked against the ledger
  (`src/relay/claim_grounding.py`); a summary that claims tests pass over a failed
  check is REFUTED even with an intact chain. A claim it cannot parse degrades to
  `unclassified`, counted against the run.
- **Proof-carrying certificate.** `--cert run.rvc` (`src/relay/cert.py`,
  `src/relay/contract.py`) writes a few-KB certificate; the vendored
  `verify_cert.py` re-derives ALLOW / UNVERIFIABLE / REFUTED offline with no model
  and no re-execution. The three verdicts are ordered: REFUTED first,
  UNVERIFIABLE next, ALLOW only when nothing earlier fired.
- **Run viewer.** `--view run.jsonl` (`src/relay/run_view.py`) draws the run as a
  hash-chained timeline; a flipped byte snaps one edge red with verdict REFUTED.
- **Verified best-of-N.** `--best-of N --check "<cmd>"` (`src/relay/verified_bon.py`)
  runs the goal N times and keeps the verified winner; a run that passed by
  editing the grader ranks below an honest higher score.
- **Regression bisection.** `--bisect run.jsonl --root <clean> --check "<cmd>"`
  (`src/relay/bisect.py`) replays the witnessed edit set and names the first edit
  that broke the check; the model is not re-run.
- **Reviewability projection.** Each `--agent` run ships a projection derived from
  the ledger (`src/relay/review.py`): `edited_unread`, `unverified_edits`, the
  failed-call scars, a `reviewability` score, and a `risk` table tiering each edit
  by mechanical signals. These are facts, not generated prose.
- **Injection-containment probe.** `--probe-injection`
  (`src/relay/injection_probe.py`) runs a fixed, readable corpus of injection
  scenarios through the permission-checked executor, assumes the model emitted the
  smuggled call, and reports containment with a re-derivable receipt. It exits
  non-zero if any scenario is not contained, so it works as a CI check. It
  generates no attacks.
- **Watch mode.** `--watch` (`src/relay/watch.py`) polls the tree for a marker
  comment (`RELAY:` by default, `--watch-marker` to change) and turns each marker
  into its own witnessed agent goal through the same gated loop.
- **Auto-commit bound to the ledger.** `--auto-commit` (`src/relay/local_git.py`)
  stages only the files the ledger recorded as edits and carries the checkpoint in
  the message; unrelated working-tree changes are left out. A failed check skips
  the commit.
- **MCP server.** `--mcp` (`src/relay/local_mcp.py`) runs a zero-dependency stdio
  JSON-RPC 2.0 server exposing ten tools (listed in the reference below). This is
  the surface Flywheel's lane layer launches.
- **Background runs.** `local_agent_start` plus the `RunRegistry`
  (`src/relay/async_runs.py`) start a long task and return a `run_id` at once, so
  a phone can poll for the result and let its request close. With `RELAY_RUN_ROOT` set,
  runs persist across a server restart.
- **Library API.** `from relay import LocalAgent, available_backends,
  build_endpoints, run_agent, SessionLedger, ToolExecutor, ToolGate`
  (`src/relay/__init__.py`).

## Stepwise usage

### As a standalone agent

1. Install it: `pip install flywheel-relay`. The bare name `relay-agent` on
   PyPI belongs to an unrelated project, so the distribution carries the
   `flywheel-` prefix while the console script stays `relay`. A source checkout
   (`pip install git+https://github.com/HarperZ9/relay.git`) still works.
2. Check which tiers are live: `relay --health --online`.
3. Ask a one-shot question: `relay "explain this function" --file app.py`.
4. Run a gated agent task, writes enabled, committed on success:
   `relay --agent "fix the off-by-one in paginate()" --root . --allow-write --auto-commit`.
5. Prove the change works by attaching your acceptance command:
   `relay --agent "fix the failing test" --root . --allow-write --check "pytest -q" --auto-commit`.
6. Save and inspect the run: add `--save run.jsonl`, then `relay --view run.jsonl`.
7. Emit and re-verify a certificate: add `--cert run.rvc`, then
   `python verify_cert.py run.rvc` (offline, zero dependencies).

### As a Flywheel lane

1. Confirm the checkout. The lane loads relay from the submodule at `relay/src`;
   if it is missing, run `git submodule update --init` from the Flywheel repo root
   (`harness/relay_bridge.py`).
2. Check lane health without spawning: `python -m harness.lanes` prints the roster,
   or call `lane_status("relay", probe=False)`.
3. Probe the live MCP server: `lane_status("relay", probe=True)` spawns
   `relay --mcp` and calls `relay.status`.
4. Run relay from the Flywheel CLI: `flywheel relay --agent "<goal>" --root . --allow-write`
   dispatches through `harness/relay_bridge.py:cmd_relay`.
5. Call a relay tool through the gateway or the generic lane caller:
   `call_lane_tool("relay", "local_agent_run", {"goal": "...", "root": ".", "allow_write": True}, governance_tier="T2")`
   (`harness/lane_caller.py`). The call is refused unless the governance tier is
   T2 or higher.

## Reference

### MCP tools

The server (`src/relay/local_mcp.py`) speaks JSON-RPC 2.0 over stdio and exposes:

- **`local_agent_health`**: reports which model tiers are live. `online=true`
  includes the online providers.
- **`local_agent_chat`**: one-shot completion from the first healthy tier, with a
  per-turn receipt id. Takes `prompt`, optional `backend`, `online`.
- **`local_agent_run`**: runs a gated agentic task and blocks until done. Takes
  `goal`, optional `root`, `allow_write`, `allow_exec`, `max_steps`, `online`.
  Returns the final answer, step count, `verified`, `chain_ok`, the ledger
  `checkpoint`, and the `intent_audit`. Write and exec are off unless allowed;
  file tools are confined to `root`; an allowed shell is not path-confined.
- **`local_agent_start`**: starts the same gated task in the background and
  returns a `run_id` at once. Same gate as `local_agent_run`.
- **`local_agent_status`**: progress of a background run: `running` / `done` /
  `error`, the step count, and the latest witnessed ledger entries.
- **`local_agent_result`**: the verified final answer and checkpoint of a
  background run once done; reports `running` until then.
- **`local_agent_runs`**: lists recent background runs. A run cut off mid-flight
  lists as `interrupted`; persisted runs (`RELAY_RUN_ROOT`) survive a restart.
- **`local_agent_sessions`**: lists saved sessions under `RELAY_SESSION_DIR`,
  each re-verified on load; pass `session_id` for the transcript.
- **`relay.status`**: liveness and identity (`ok`, `server`, `version`,
  `protocol`). Network-free. This is the lane's declared health tool.
- **`relay.doctor`**: identity plus the configured local tiers, the exposed tool
  names, and remote state. Network-free.

### CLI flags

From `src/relay/local_agent_cli.py`:

- Model selection and I/O: `--health`, `--backend`, `--model`, `--file`
  (repeatable), `--system`, `--max-tokens`, `--temperature`, `--seed`,
  `--serve-url`, `--ollama-url`, `--json`, `--stream`, `--online`, `--providers`.
- Agent loop: `--agent`, `--root`, `--allow-write`, `--allow-exec`,
  `--interactive`, `--no-repo-map`, `--no-conventions`, `--max-steps`,
  `--compact-budget`.
- Proof and selection: `--check`, `--test-cmd`, `--best-of`, `--review`, `--save`,
  `--auto-commit`, `--cert`, `--contract`, `--verify-cert`, `--bisect`, `--view`,
  `--no-color`.
- Watch, probe, and server modes: `--probe-injection`, `--watch`, `--watch-marker`,
  `--watch-interval`, `--mcp`.

### Environment variables

- `<PROVIDER>_API_KEY`, `<PROVIDER>_PROVIDER_KEY`, `<PROVIDER>_PROVIDER_BASE_URL`,
  `<PROVIDER>_CLOUD_BASE_URL`, `<PROVIDER>_CLOUD_KEY`: feed the endpoint ladder.
- `RELAY_RUN_ROOT`: persist background runs across a restart.
- `RELAY_SESSION_DIR`: where saved session ledgers live.
- `FLYWHEEL_RELAY_URL`: points the lane at a remote deployment (from the lane's
  `env_url_var`, applicable when the lane is reached remotely).

### Lane declaration

From `harness/lanes_registry.py`:

- name `relay`, install_name `flywheel-relay`, command `relay`, args
  `("--mcp",)`, kind `pip`, version `0.2.5`, organ `execution`, py_module
  `relay.local_mcp`, source_repo `public/relay`.
- `package_disabled_reason` is empty: `flywheel-relay` is published, so the
  package install profile is live and the source checkout is the fallback.
- Minimum governance tier `T2` (`harness/lane_caller.py:LANE_MIN_TIERS`), because
  the lane can run code through `run`/exec.

### Verdicts and honest nulls

- The verifier orders REFUTED > UNVERIFIABLE > ALLOW, so a clause it cannot
  re-derive is never rounded up to a pass. Five of the eight contract clauses
  re-derive from the certificate alone; three (`tests_pass`, `reviewability`,
  `claim_grounded`) need the in-tree verifier and report unverifiable in the
  vendored file (README "The proof toolkit"; `docs/ACCOUNTABILITY.md`).
- The certificate proves re-derivable correctness, not authorship. Python's
  standard library carries no asymmetric signature, so an `.rvc` says the recorded
  run holds, not who produced it (`docs/ACCOUNTABILITY.md`).
- Claim grounding is rule-based; an unparseable claim degrades to `unclassified`.
- Verified best-of-N is decisive only when a runnable check exists; with no check
  it ranks accountability, not capability.
- Bisection assumes the pre-run tree state, a deterministic check, and a failure
  monotonic in the edit prefix.
- The `run` denylist refuses a few literal destructive spellings; the README
  states it is a guardrail against a small model wrecking the tree. It is not a
  security boundary.
- Version note (observed 2026-09-18): the lane registry and the bundled-lane
  expectation declare relay `0.2.0`, while the read source checkout's package
  manifest and MCP server report `0.1.0`. A live probe compares the reported
  version against `0.2.0`, so until the source version is aligned the probe can
  return `stale` on the version check even when the server answers
  (`harness/lanes.py:_health_verdict`). This is a version-pin mismatch in the read
  checkout. The runtime has not failed.

## Composition

### Which seam relay is

Relay is the `execution` organ in the lane layer. Where the other lanes perceive
(`gather`), verify (`crucible`), map structure (`index`), orchestrate (`forum`),
or remember (`mneme`), relay is the seam that changes a working tree and leaves a
provable record of having done so. The gateway treats it as the single
phone-facing execution origin: `harness/gateway_lane_calls.py:_relay_mcp_call`
forwards one relay MCP tool at a time and degrades to an honest error dict if the
lane is down, so a dead lane never takes the origin with it.

### What it consumes from peers

- A **goal** string, plus `root` and the write/exec gates. In a bare run this
  comes from the operator; in a composed run a peer supplies it (an orchestration
  lane like `forum`, or a research finding from `gather` reduced to a task).
- A **governance tier**. `harness/lane_caller.py:call_lane_tool` refuses a relay
  call whose tier is below `T2`, and `_relay_start_not_admitted` returns a 403
  `CAPABILITY_NOT_ADMITTED` until model and run custody is admitted. In a frozen
  gateway build the bundled-lane expectation admits only `relay.status` by default
  (`harness/bundled_lane_expectations.py`, enforced by `launch_allows_tool`), so
  the executing tools stay closed until they are staged in explicitly.
- An **acceptance command** (`--check`), which carries the caller's authority and
  runs outside the model's tool boundary.

### What it emits for peers

- A **witnessed run**: a `run_id`, a ledger `checkpoint`, the `verified`
  composite, and the `intent_audit`, returned by `local_agent_run` /
  `local_agent_result`. These are the same receipts a desktop run produces.
- A **re-verifiable certificate** (`.rvc`) that any party re-checks offline with
  the vendored `verify_cert.py`, and a **reviewability projection** and **risk
  table** that a downstream surface can enforce because they are facts, not prose.

The downstream re-check is by re-derivation. A verification lane such as
`crucible`, or a stranger with `verify_cert.py`, can re-derive the verdict from
the certificate. Relay does not itself push its certificate into another lane; the
observed wiring is the gateway forwarding relay's tools and the governance envelope
enforcing the tier. Treat "crucible re-checks the certificate" as the intended
composition the artifact is built for. No automatic pipeline wires it together in
code today.

### Worked example: forum routes, relay executes, the run is re-verifiable

A caller wants a task routed by policy, executed under custody, and left as a
record a reviewer can check. The two lanes plug together through the generic lane
caller.

```python
from harness.lane_caller import call_lane_tool

# 1. Orchestration decides the task belongs to the execution organ.
#    (forum is T1; here it has produced the goal to hand off.)
goal = "fix the failing test in paginate() and keep the public API stable"

# 2. The gateway forwards the run to relay, gated at T2. A tier below T2 is
#    refused before the lane is ever spawned.
run = call_lane_tool(
    "relay",
    "local_agent_run",
    {"goal": goal, "root": ".", "allow_write": True, "max_steps": 8},
    governance_tier="T2",
)

# 3. relay returns a witnessed result: the ledger checkpoint, the verified
#    composite, and the intent audit.
checkpoint = run["checkpoint"]
verified = run["verified"]
audit = run["intent_audit"]
```

To make acceptance something the run earns, the caller runs relay from the
CLI with an acceptance check and a certificate, then hands the certificate to a
reviewer or a verification step:

```bash
flywheel relay --agent "fix the failing test in paginate()" --root . \
  --allow-write --check "pytest -q" --cert run.rvc --save run.jsonl
python verify_cert.py run.rvc      # ALLOW / UNVERIFIABLE / REFUTED, offline
```

The seam holds because each side keeps its own authority: orchestration chooses
what runs, the governance tier decides whether relay may run it, relay decides
nothing about whether the work is correct, and the acceptance check (the caller's
command) plus the offline verifier decide that last question without trusting the
model or relay's own summary.