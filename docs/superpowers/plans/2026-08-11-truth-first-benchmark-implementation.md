# Truth-first lane repair and benchmark baseline implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair Flywheel lane-health truth and produce a re-checkable
Codex-versus-Flywheel Spark pilot plus a separately reported local-model
baseline over the same admitted tasks.

**Architecture:** A source-aware child launch specification fixes lane probes
without changing the public argv roster. The existing cross-harness manifest,
scorecard, run-receipt, coverage, comparison, outcome, and schematic contracts
remain the benchmark spine. One executor expands planned rows, delegates calls
through injected adapters, runs deterministic artifact oracles, binds receipts,
and emits inputs for the existing synthesizers.

**Tech Stack:** Python 3 standard library, pytest, JSON/JSONL receipts, MCP over
stdio, Codex CLI, Flywheel `RouterAgent` and `local_loop`, OpenAI-compatible
local endpoints.

## Global constraints

- Modify only this Flywheel repository. Write raw run evidence and operator
  reports under an operator-supplied external project-docs experiment root.
- Do not touch portfolio, Retro, shader, Claude-session, creative, deployment,
  publication, or outreach files.
- Preserve zero mandatory external dependencies. New Python modules and tests
  must stay at or below 300 lines. Grandfathered files must not grow.
- Record pre-edit line counts for every modified file under `harness/`,
  `scripts/`, and `tests/`. Treat `harness/lanes.py`,
  `harness/cross_harness_manifest.py`, `scripts/run_harness_cli.py`, and the
  Task 7 consumers as zero-growth budgets. Land helpers only in the focused
  sub-300-line modules named in this plan; do not bypass the ratchet ledger.
- Do not create a parallel benchmark, task-set, scorecard, or receipt schema.
- Treat `agt-001`, `agt-003`, `agt-009`, and `agt-010` as selectors only.
  Persist their full canonical task IDs in prompts, rows, receipts, and keys.
- The Spark pilot has exactly 24 planned rows: four tasks, two roles, three
  repetitions. The local baseline has exactly eight planned rows: four tasks,
  two roles, one repetition. Never combine their denominators.
- A blocked role still emits every planned row as typed `unavailable`. Blocked
  rows never become zero-quality or zero-latency observations.
- Availability reports four distinct counts for each cohort: `planned`,
  `admitted`, `blocked`, and `launched`. `admitted` means the static and live
  gates permitted an attempt; it is never inferred from process launch alone.
- Every launched attempt runs in its own temporary, read-only task workspace
  materialized from only the admitted inputs. The Flywheel source tree is not
  an attempt workspace and must hash identically before and after execution.
- Do not execute the 84-attempt expansion in this plan.
- Do not start a local service, alter credentials, or read credential values.
  Fresh gates may probe already configured endpoints.
- Use TDD for every behavior change. Stage exact files, scan for secrets and
  host paths, and commit only after focused tests and the file gate pass.
- Use the existing feature branch. Preserve unrelated worktree state.

## File responsibility map

- `harness/mcp_client.py`: child process launch authority only.
- `harness/lanes.py`: source resolution, roster truth, probe semantics.
- `harness/context_envelope.py`, `harness/gateway.py`,
  `harness/lane_caller.py`, and runtime paths in `harness/plugins.py`: consume
  source-aware launch specs; public plugin metadata stays portable.
- `harness/cli_entry.py`: umbrella `lanes --probe` forwarding and packaged
  `cross-harness-execute` dispatch only.
- `harness/adapter_runtime_matrix.py`: metadata-only admission truth.
- `harness/cross_harness_manifest.py`: replayable prompt and oracle projection.
- `harness/cross_harness_oracles.py`: deterministic artifact checkers only.
- `harness/cross_harness_executor.py`: row expansion, state, receipts, outputs.
- `harness/cross_harness_types.py`: shared immutable attempt/result types.
- `harness/cross_harness_artifacts.py`: isolated workspaces, materialization,
  source snapshots, receipt binding, and artifact indexing.
- `harness/cross_harness_adapters.py`: injected provider execution boundaries.
- `harness/cross_harness_cli.py`: packaged executor CLI used by the console
  entrypoint and the source-checkout wrapper.
- `harness/cross_harness_seed_steps.py`: exact admission/Spark/local steps for
  the existing seed orchestrator; it does not execute providers itself.
- `scripts/run_cross_harness_execution.py`: operator CLI and file I/O.
- Existing profile, coverage, comparison, outcome, matrix, and schematic files:
  consume executor evidence without duplicating it.

---

### Task 1: Add child-only MCP launch specifications

**Files:**
- Modify: `harness/mcp_client.py:27-117`
- Modify: `tests/test_mcp_client.py`

**Interfaces:**
- Produces: `LaunchSpec(argv, cwd, env_overrides)` accepted by `StdioTransport`
  and `MCPClient`.
- Preserves: plain `list[str]` launch calls and list-only `open_mcp()`.

- [ ] **Step 1: Write failing transport tests**

```python
def test_stdio_transport_launch_spec_forwards_cwd_and_merged_child_env(monkeypatch):
    class EmptyStream:
        def __iter__(self):
            return iter(())
    class FakeProc:
        stdin = None
        stdout = EmptyStream()
        stderr = EmptyStream()
        def poll(self):
            return None
    seen = {}
    monkeypatch.setattr(subprocess, "Popen", lambda argv, **kw: seen.update(argv=argv, **kw) or FakeProc())
    StdioTransport(LaunchSpec(("python", "-m", "demo"), "/repo", (("PYTHONPATH", "/repo"),)))
    assert seen["argv"] == ["python", "-m", "demo"]
    assert seen["cwd"] == "/repo"
    assert seen["env"]["PYTHONPATH"] == "/repo"
```

Add companion tests proving the parent environment is unchanged and a plain
argv list keeps the old `Popen` contract. Add a failing double-start test that
enters an already-started `MCPClient` context and proves `Popen` and MCP
`initialize` each occur exactly once.

- [ ] **Step 2: Run the new tests and record RED**

Run: `python -m pytest tests/test_mcp_client.py -q`

Expected: FAIL because `LaunchSpec` does not exist.

- [ ] **Step 3: Implement the minimal immutable launch type**

```python
@dataclass(frozen=True)
class LaunchSpec:
    argv: tuple[str, ...]
    cwd: str | None = None
    env_overrides: tuple[tuple[str, str], ...] = ()
```

When a launch spec is supplied, copy `os.environ`, apply only its overrides,
and pass `cwd` and the child environment to `Popen`. Do not mutate the parent.
Make `MCPClient.start()` return immediately when already started so a context
manager cannot initialize twice.

- [ ] **Step 4: Run focused tests and the file gate**

Run:

```text
python -m pytest tests/test_mcp_client.py -q
python scripts/check_file_gate.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```text
git add harness/mcp_client.py tests/test_mcp_client.py
git commit -m "feat: add bounded MCP child launch specs"
```

### Task 2: Repair source resolution and live-probe truth

**Files:**
- Modify: `harness/lanes.py:1-343`
- Modify: `harness/cli_entry.py:164-181`
- Modify: `harness/context_envelope.py`
- Modify: `harness/gateway.py`
- Modify: `harness/lane_caller.py`
- Modify: `harness/plugins.py`
- Modify: `tests/test_lanes.py`
- Modify: `tests/test_cli_launch.py`
- Test: `tests/test_lane_launch.py`
- Test: `tests/test_plugins.py`
- Modify: `tests/test_context_envelope.py`
- Modify: tests covering gateway and lane-caller execution.

**Interfaces:**
- Consumes: `LaunchSpec` from Task 1.
- Produces: `resolve_source_repo(lane) -> Path | None` and
  `resolve_mcp_launch(name) -> LaunchSpec`.
- Preserves: `resolve_mcp_command(name) -> list[str]` for public JSON rosters.

- [ ] **Step 1: Write resolver, probe, and CLI RED tests**

Cover explicit `FLYWHEEL_WORKSPACE_ROOT`, inferred workspace, matching-container
sibling, absent checkout, Python child `cwd`/`PYTHONPATH`, absolute Node script,
source install, source-only probe, install-only roster, failed probe, missing
health tool, health-tool error, and `lanes --probe` forwarding.

```python
def test_lanes_probe_flag_is_forwarded_to_roster(monkeypatch):
    calls = []
    monkeypatch.setattr("harness.lanes.lane_roster", lambda **kw: calls.append(kw) or roster())
    assert cli_entry._dispatch_umbrella("lanes", ["--probe"]) == 0
    assert calls == [{"probe": True}]
```

- [ ] **Step 2: Run three representative tests and record RED**

```text
python -m pytest tests/test_lanes.py::test_source_checkout_is_probed_when_package_is_absent -v
python -m pytest tests/test_cli_launch.py::test_lanes_probe_flag_is_forwarded_to_roster -v
python -m pytest tests/test_lanes.py::test_presence_only_installed_lane_is_declared_not_live -v
```

- [ ] **Step 3: Centralize source resolution and launch selection**

```python
def resolve_source_repo(lane: Lane) -> Path | None:
    candidates = []
    if os.environ.get("FLYWHEEL_WORKSPACE_ROOT"):
        candidates.append(Path(os.environ["FLYWHEEL_WORKSPACE_ROOT"]) / lane.source_repo)
    candidates.extend(_inferred_source_candidates(REPO, lane.source_repo))
    return next((p.resolve() for p in _dedupe(candidates) if p.is_dir()), None)

def resolve_mcp_command(name: str) -> list[str]:
    # Portable declared command only. Safe for public roster serialization.
    return _portable_declared_command(LANES[name])

def resolve_mcp_launch(name: str) -> LaunchSpec:
    # Runtime-only source/package resolution. May contain local cwd/env facts.
    return _source_aware_launch(LANES[name], resolve_source_repo(LANES[name]))
```

Python source launches use the current interpreter, source checkout `cwd`, and
a child-only `PYTHONPATH` prefix. Node launches use an absolute script. Frozen
builds retain existing bare-command behavior. Source-profile install must fail
without invoking pip/npm when no checkout resolves. `plugin_roster()` and every
other public JSON surface use only `resolve_mcp_command()`. Lane probing,
context-envelope gathering, gateway forum proxying, lane calls, and plugin
probe/call execution use `resolve_mcp_launch()` so `cwd` and child environment
cannot be lost. Tests reject host paths in serialized rosters and prove every
runtime consumer receives a `LaunchSpec`.

- [ ] **Step 4: Make probe state evidence-derived**

Presence-only rows are `declared`, never `live`. A source checkout reaches the
probe even when no package is installed. A live verdict requires initialization,
tool listing, a status/doctor tool, and an `ok` response. Health-call errors or
missing health tools are `stale`; launch failures are `declared` when source or
package presence exists and `missing` only when neither exists. Remove the
duplicate `start()` call.

- [ ] **Step 5: Run lane regression suites and file gate**

```text
python -m pytest tests/test_mcp_client.py tests/test_lanes.py tests/test_cli_launch.py -q
python -m pytest tests/test_lane_launch.py tests/test_plugins.py tests/test_probe_tool_specs.py tests/test_context_envelope.py tests/test_lane_caller.py tests/test_gateway.py -q
python scripts/check_file_gate.py
```

Shrink comments or dead imports so frozen `harness/lanes.py` does not grow.

- [ ] **Step 6: Commit**

```text
git add harness/lanes.py harness/cli_entry.py harness/context_envelope.py harness/gateway.py harness/lane_caller.py harness/plugins.py tests/test_lanes.py tests/test_cli_launch.py tests/test_context_envelope.py tests/test_lane_launch.py tests/test_lane_caller.py tests/test_plugins.py tests/test_gateway.py
git commit -m "fix: report live lane probe truth"
```

### Task 3: Derive endpoint admission from fresh gate evidence

**Files:**
- Modify: `harness/adapter_runtime_matrix.py:34-244`
- Modify: `scripts/run_adapter_runtime_matrix.py`
- Modify: `scripts/run_model_endpoint_gate.py`
- Modify: `tests/test_adapter_runtime_matrix.py`
- Modify: `tests/test_model_endpoint_gate.py`

**Interfaces:**
- Produces: optional `endpoint_gate`, path, and hash inputs to `build_matrix()`.
- Produces: sanitized `endpoint_gate_matches` and exact `blocking_gates`.

- [ ] **Step 1: Add RED fixtures for every readiness mismatch**

Test passing, missing, failed, wrong model, wrong backend, wrong profile hash,
wrong observed reference, missing Ollama digest, missing/invalid timestamps,
future timestamps, stale gate rows, and run-ID mismatch. Also prove both Spark
roles require Codex CLI presence and that manifest readiness alone cannot imply
focused-run readiness. Inject `now` into every freshness test.

- [ ] **Step 2: Run focused tests and record RED**

Run: `python -m pytest tests/test_adapter_runtime_matrix.py tests/test_model_endpoint_gate.py -q`

- [ ] **Step 3: Emit and join exact gate identity**

Extend endpoint-gate output with canonical profile SHA-256, selected profile ID,
expected and observed model references, backend, health/generation booleans,
failure class, Ollama tag digest when applicable, `run_id`, and RFC 3339 UTC
`observed_at`. Compute local readiness only when all selected fields match.
The matrix receives `expected_gate_run_id`, an injected `now`, and
`max_age_seconds=900`. A gate is fresh only when its run ID matches and
`-30 <= (now - observed_at).total_seconds() <= 900`; the 30-second negative
allowance is clock skew, not extra age. Emit exact failure codes
`endpoint_gate_timestamp_missing`, `endpoint_gate_timestamp_invalid`,
`endpoint_gate_from_future`, `endpoint_gate_stale`, and
`endpoint_gate_run_mismatch`. Static auth evidence must say
`cli_presence_only`; the admission smoke remains the live account/model gate.

- [ ] **Step 4: Add `--endpoint-gate` to the metadata-only CLI**

The runtime-matrix command reads the supplied JSON and its SHA-256, expected
gate run ID, and maximum age. It must not probe endpoints, providers, model
weights, token stores, or credential values.

- [ ] **Step 5: Run tests and gates, then commit**

```text
python -m pytest tests/test_adapter_runtime_matrix.py tests/test_model_endpoint_gate.py -q
python scripts/check_file_gate.py
git add harness/adapter_runtime_matrix.py scripts/run_adapter_runtime_matrix.py scripts/run_model_endpoint_gate.py tests/test_adapter_runtime_matrix.py tests/test_model_endpoint_gate.py
git commit -m "fix: derive local route readiness from endpoint gates"
```

### Task 4: Make the four pilot tasks replayable and deterministic

**Files:**
- Modify: `benchmarks/agentic-task-set-v1.json`
- Modify: `benchmarks/cross-harness-adapter-contract-v1.json`
- Create: `benchmarks/fixtures/cross-harness/index-events-v1.json`
- Create: `benchmarks/fixtures/cross-harness/shared-task-facts-v1.json`
- Create: `benchmarks/fixtures/cross-harness/paired-friction-observations-v1.json`
- Create: `benchmarks/fixtures/cross-harness/documentation-topology-v1.json`
- Modify: `harness/cross_harness_manifest.py:74-342`
- Modify: `scripts/run_cross_harness_manifest.py`
- Create: `harness/cross_harness_oracles.py`
- Modify: `tests/test_cross_harness_manifest.py`
- Create: `tests/test_cross_harness_oracles.py`

**Interfaces:**
- Produces task rows with full `raw_prompt`, `oracle`, input hashes, and a
  response envelope contract.
- Produces `evaluate_task_oracle(context: OracleContext) -> OracleResult`.

- [ ] **Step 1: Write manifest and oracle RED tests**

```python
def test_manifest_preserves_replayable_prompt_and_oracle():
    row = build_manifest(task_set(), contract())["task_rows"][0]
    assert sha256_text(row["raw_prompt"]) == row["raw_prompt_sha256"]
    assert row["oracle"]["checker_id"] == "index_fallback_integrity/v1"
```

Test exact artifact basenames, required JSON fields, forbidden overclaims,
missing oracle as `unverifiable`, and one positive and negative fixture per
checker. Use the preregistered predicates below; fixtures must name every
failure code and prove that object-key order and JSON whitespace do not change
the verdict.

- [ ] **Step 2: Run tests and record RED**

Run: `python -m pytest tests/test_cross_harness_manifest.py tests/test_cross_harness_oracles.py -q`

- [ ] **Step 3: Clean and extend existing benchmark contracts**

Convert every host path in both JSON files to a repository-relative input or a
typed public-clean `workspace://`, `external://`, or `operator://` reference.
The four pilot tasks must use individual repository-relative files so every
admitted byte receives a complete SHA-256. Non-pilot typed external inputs stay
unresolved until their own admission task. Add these pilot checker IDs:

```text
index_fallback_integrity/v1
shared_task_artifact/v1
paired_friction/v1
documentation_maintenance/v1
```

Remove archived checkout, user-profile, drive-root, and temporary paths from the
adapter contract. Add explicit `adapter_id` values and local endpoint selectors.
Append one JSON-only response envelope to each prompt:

```json
{"artifacts":{"<declared filename>":"<markdown string or JSON object>"}}
```

- [ ] **Step 4: Implement independent artifact oracles**

```python
@dataclass(frozen=True)
class OracleContext:
    task_id: str
    oracle_spec: dict[str, Any]
    raw_output_path: Path
    artifact_paths: dict[str, Path]
    expected_input_sha256s: dict[str, str]
    scorecard_core: dict[str, Any]

@dataclass(frozen=True)
class OracleResult:
    state: str
    checker_id: str
    checker_version: str
    evidence: dict[str, Any]
    failure_codes: list[str]
    checked_artifacts: list[dict[str, str]]
```

Oracles inspect materialized bytes and executor facts, never provider self-scores.
Structural completion is deterministic. Qualitative observations remain under
`secondary_rubric` and cannot change oracle state.

Apply these common predicates before the task checker: expected basenames match
exactly; both declared files exist, are regular UTF-8 files, and are nonempty;
the JSON parses with duplicate keys rejected; its `task_id` equals the canonical
task; its `input_sha256s` equals executor facts exactly; and the Markdown names
the canonical task ID. JSON object order and insignificant whitespace are
ignored. Arrays retain order. Common failure codes are
`artifact_set_mismatch`, `artifact_not_regular`, `artifact_not_utf8`,
`artifact_empty`, `json_invalid`, `json_duplicate_key`, `task_id_mismatch`,
`input_hash_mismatch`, and `markdown_task_id_missing`.

Preregister the four task predicates and their task-specific failure codes:

1. `index_fallback_integrity/v1`: independently derive the expected failure
   classes from the admitted event fixture's typed events. Derive stale
   preservation from equal before/after artifact hashes and whether an MCP
   health claim is supportable from a successful-call event. Compare the
   provider's class list and cited event IDs to those derived facts; scan both
   artifacts for an unsupported health claim. Fail with
   `failure_classes_mismatch`, `event_citation_mismatch`,
   `stale_artifact_mutated`, `unsupported_mcp_health_claim`, or
   `receipt_input_hash_mismatch`. Ignore provider-authored preservation/health
   booleans when deciding pass.
2. `shared_task_artifact/v1`: compare JSON `raw_prompt_sha256`,
   `input_sha256s`, and `tool_policy_sha256` to executor facts. Resolve every
   relative `raw_artifact_path` and `receipt_path` below the attempt directory,
   require it to exist, and compare its hash to executor material. Derive
   failure modes from the executor's orthogonal states, not from the provider's
   labels. Reject absolute/parent paths and the normalized phrases
   `same model behavior`, `identical controls`, and `pure harness ablation`.
   Fail with `prompt_hash_mismatch`, `tool_policy_hash_mismatch`,
   `raw_artifact_path_invalid`, `raw_artifact_hash_mismatch`,
   `failure_modes_mismatch`, `receipt_path_invalid`, or `forbidden_claim`.
3. `paired_friction/v1`: derive exact modes, unique task keys, paired rows,
   denominator, and safety-control state from the admitted observation fixture.
   Compare provider aggregates to that independently computed result. The
   fixture must contain one observation for each exact mode per task key, a
   nonzero denominator, and no disabled required safety control. Fail with
   `fixture_mode_set_invalid`, `fixture_pair_incomplete`,
   `reported_task_keys_mismatch`, `reported_pair_mismatch`,
   `denominator_mismatch`, or `fixture_safety_control_disabled`. Ignore a
   provider-authored `safety_systems_disabled` value when deciding pass.
4. `documentation_maintenance/v1`: derive the exact four expected surfaces and
   their repository-relative paths/code references from the admitted topology
   fixture. Compare provider output to those derived mappings, resolve every
   reference below the task workspace, and run the shared public-claim scan over
   both output artifacts. Fail with `fixture_surface_set_invalid`,
   `surface_set_mismatch`, `surface_path_invalid`, `code_refs_mismatch`, or
   `claim_language_violation`. Ignore provider-authored `synchronized` or gate
   status fields when deciding pass.

Each checker returns every applicable code in stable sorted order and hashes
every checked artifact. A missing checker configuration returns
`unverifiable`; malformed provider output returns `malformed` before oracle
evaluation. These rules are frozen in task-set oracle metadata and fixtures
before any live attempt. Positive fixtures contain the raw facts, never an
answer key; negative fixtures mutate one fact or provider artifact at a time and
assert the exact failure-code set. No provider-authored boolean or score can set
deterministic quality.

- [ ] **Step 5: Run tests, hygiene, and commit**

```text
python -m pytest tests/test_cross_harness_manifest.py tests/test_cross_harness_oracles.py -q
python scripts/check_file_gate.py
python scripts/check_public_instructions.py
git add benchmarks/agentic-task-set-v1.json benchmarks/cross-harness-adapter-contract-v1.json benchmarks/fixtures/cross-harness/index-events-v1.json benchmarks/fixtures/cross-harness/shared-task-facts-v1.json benchmarks/fixtures/cross-harness/paired-friction-observations-v1.json benchmarks/fixtures/cross-harness/documentation-topology-v1.json harness/cross_harness_manifest.py harness/cross_harness_oracles.py scripts/run_cross_harness_manifest.py tests/test_cross_harness_manifest.py tests/test_cross_harness_oracles.py
git commit -m "feat: add deterministic cross-harness oracles"
```

### Task 5: Implement row expansion, orthogonal state, and receipts

**Files:**
- Create: `harness/cross_harness_types.py`
- Create: `harness/cross_harness_artifacts.py`
- Create: `harness/cross_harness_executor.py`
- Create: `tests/test_cross_harness_artifacts.py`
- Create: `tests/test_cross_harness_executor.py`

**Interfaces:**
- `cross_harness_types.py` produces `AttemptRequest`, `AvailabilityResult`,
  `EnforcementResult`, `AdapterResult`, and `CrossHarnessAdapter`.
- `cross_harness_artifacts.py` produces source snapshots, isolated task
  workspaces, response-envelope materialization, receipt binding/recheck, and
  the artifact index.
- `cross_harness_executor.py` produces `execute_cross_harness_manifest()`,
  `resolve_task_ids()`, `derive_primary_outcome()`, and `comparison_key()`.

- [ ] **Step 1: Write RED tests for selection, row counts, states, and tamper**

First cover exact and short selectors, unknown/ambiguous selectors, 24 and
eight-row expansion, phase/run path uniqueness, and duplicate attempt keys.
Then add separate RED tests for unavailable, timeout, malformed, internal error,
oracle fail, unverifiable, receipt drift, precedence, workspace isolation,
source metadata preservation, artifact-root containment including a symlinked
root, artifact indexing, and receipt tampering. Do not write one broad test
before all boundaries exist.

- [ ] **Step 2: Run tests and record RED**

Run:
`python -m pytest tests/test_cross_harness_executor.py tests/test_cross_harness_artifacts.py -q`

- [ ] **Step 3: Implement the typed request and adapter boundary**

```python
@dataclass(frozen=True)
class AttemptRequest:
    run_id: str
    phase: str
    task_set_id: str
    task_id: str
    prompt: str
    raw_prompt_sha256: str
    provider_role: str
    harness_id: str
    adapter_id: str
    model_id: str
    workspace_root: Path
    workspace_snapshot_sha256: str
    input_sha256s: dict[str, str]
    tool_policy: dict[str, Any]
    tool_policy_sha256: str
    repetition: int
    cache_state: str
    timeout_seconds: int
    artifact_dir: Path

@dataclass(frozen=True)
class AvailabilityResult:
    available: bool
    failure_class: str
    detail: str
    evidence: dict[str, Any]

@dataclass(frozen=True)
class EnforcementResult:
    description: dict[str, Any]
    description_sha256: str
    verification_state: str
    equivalence_class: str

@dataclass(frozen=True)
class AdapterResult:
    execution_state: str
    output_text: str
    tool_trace: list[dict[str, Any]]
    elapsed_ms: int
    model_observed: str
    randomness_control: str
    failure_class: str
    failure_detail: str
    resource_observation: dict[str, Any]
    usage: dict[str, Any]
    observed_capabilities: list[str]
    policy_violations: list[str]

class CrossHarnessAdapter(Protocol):
    role: str
    adapter_id: str
    def enforcement(self, request: AttemptRequest) -> EnforcementResult: ...
    def availability(self, request: AttemptRequest) -> AvailabilityResult: ...
    def execute(self, request: AttemptRequest) -> AdapterResult: ...
```

The shared tool policy is exactly:

```python
{"version": "cross-harness-read-only/v1", "allow_read": True,
 "allow_write": False, "allow_exec": False, "allow_mcp": False,
 "max_steps": 6, "max_output_tokens": 2048}
```

This is the common declared policy, not proof of equivalent enforcement. Each
adapter exposes and hashes its actual enforcement description before
availability is decided, including for unavailable rows. The direct
Codex row records read-only filesystem sandbox, ephemeral session, visible CLI
configuration boundary, and any observed shell/MCP/tool capabilities. The
Flywheel row records `ToolGate` permissions, step budget, and proposer boundary.
Set the row's `policy_equivalence="non_equivalent"` unless a fixture and live
smoke prove the effective capability sets identical. Keep the shared declared-policy hash
in the comparison key, but retain distinct enforcement hashes in every row and
label the pilot policy-non-equivalent in comparison and outcome reports. Never
describe matching declared hashes as matching controls.

- [ ] **Step 4: Implement orthogonal axes and derived precedence**

Persist `execution_state`, `oracle_state`, and `receipt_state`. Derive one
primary outcome in this order: unavailable, timeout, internal error, malformed,
receipt drift, unverifiable, oracle fail, completed. Preserve the source axes.
Map the derived outcome back to the existing scorecard `status` values:

```text
completed, oracle_fail, unverifiable -> executed
unavailable                         -> skipped
timeout, malformed, internal_error  -> failed
receipt_drift                       -> invalid
```

- [ ] **Step 5: Materialize only declared artifacts and bind receipts**

Reject absolute paths, parent traversal, duplicate names, missing declared
names, and undeclared names as malformed. Write each attempt below
`<run-id>/<phase>/<role>/<canonical-task>/rep-NNN/`. Bind the scorecard row
with canonical JSON SHA-256 and make `recheck_attempt_receipt()` independently
recompute it.
The run-root `artifact-index.json` hashes every referenced artifact and states
explicitly that the index cannot contain its own hash.

Before invoking an adapter, create a unique temporary task workspace below the
external run root. Materialize only the task inputs admitted by the manifest
using independent copies or a platform reflink proven not to share metadata;
never use hardlinks. Make the copies read-only and pass that directory as
`AttemptRequest.workspace_root`. Never let an adapter write into the Flywheel
checkout. Preserve a failed attempt's workspace below its artifact directory;
remove a successful workspace only after artifact and receipt rechecks pass.
Record a deterministic source-tree snapshot before the first attempt and after
the last attempt, including relative path, byte hash, size, mode, and platform
read-only attributes, and fail the run if they differ.

Before creating any directory, resolve the existing source root strictly and
the proposed artifact root through its nearest existing parent. Reject equality
or containment under the source root, including case-normalized Windows paths,
symlinks, and junctions, with `artifact_root_inside_source`. Different-drive
paths are allowed after normal resolution. This executable preflight enforces
the external-artifact boundary; `${ROOT}` naming alone does not.

- [ ] **Step 6: Run tests and commit**

```text
python -m pytest tests/test_cross_harness_executor.py tests/test_cross_harness_artifacts.py tests/test_cross_harness_oracles.py -q
python scripts/check_file_gate.py
git add harness/cross_harness_types.py harness/cross_harness_artifacts.py harness/cross_harness_executor.py tests/test_cross_harness_artifacts.py tests/test_cross_harness_executor.py
git commit -m "feat: execute typed cross-harness attempts"
```

### Task 6: Add injected Codex, Flywheel, and local adapters plus CLI

**Files:**
- Create: `harness/cross_harness_adapters.py`
- Create: `harness/cross_harness_cli.py`
- Create: `tests/test_cross_harness_adapters.py`
- Create: `scripts/run_cross_harness_execution.py`
- Modify: `harness/cli_entry.py`
- Modify: `tests/test_cli_launch.py`
- Modify: `scripts/run_harness_cli.py`
- Modify: `tests/test_harness_cli.py`

**Interfaces:**
- Consumes Task 5 adapter protocol.
- Produces adapter registry and a packaged `flywheel cross-harness-execute`
  command. The script is a thin wrapper over `harness.cross_harness_cli.main`.

- [ ] **Step 1: Write adapter and command-construction RED tests**

Inject the process runner and proposer. Test Codex argv, JSONL trace capture,
explicit usage nulls, timeout, nonzero exit, Flywheel ledger/checkpoint capture,
read-only tool gate, distinct actual-enforcement hashes, policy-non-equivalence,
local endpoint selection, help text from a bare installed-package fixture, and
exact CLI forwarding through both entrypoints.

- [ ] **Step 2: Run tests and record RED**

Run:
`python -m pytest tests/test_cross_harness_adapters.py tests/test_harness_cli.py tests/test_cli_launch.py -q`

- [ ] **Step 3: Implement the direct Codex adapter**

Construct the platform-resolved equivalent of:

```text
codex exec --model 5.3-Codex-Spark --sandbox read-only --cd <workspace> --ephemeral --json --output-last-message <output> <prompt>
```

Capture stdout JSONL as the tool trace. Record randomness as `unsupported`
unless the live CLI exposes a verified control. Missing usage stays null with
`provider_usage_unavailable`. Record the actual Codex enforcement description
and hash separately from the shared declared policy. Audit the JSONL trace for
observed tool, shell, MCP, and write attempts; a disallowed action is a policy
conformance failure, not evidence that the two adapters had equal controls.

- [ ] **Step 4: Implement Flywheel and local RouterAgent adapters**

Both routes use `RouterAgent` plus `local_loop.run_agent` and a read-only
`ToolExecutor`. The Spark Flywheel adapter uses the same requested model through
the Codex CLI proposer boundary. Local adapters use only the uniquely selected,
fresh-gated endpoint. Preserve ledger, tool events, checkpoint, verification,
observed model, elapsed time, and explicit resource/usage nulls.

The CLI proposer implements the existing proposer protocol exactly:

```python
class CodexCliProposer:
    model_ref: str
    events: list[dict[str, Any]]
    def generate(self, prompt: str, *, seed: int, temperature: float,
                 max_new_tokens: int, system: str = "") -> ProposerOutput: ...
```

It returns `ProposerOutput` from `harness.proposer`; it does not add a second
agent loop or inference contract.

- [ ] **Step 5: Register the operator command**

Required arguments: manifest, runtime matrix, artifact root, task selectors,
roles, repetitions, source commit, source root, phase, timeout, cache state,
optional endpoint gate, gate run ID, optional admission receipt for later
phases, maximum gate age, and `--strict-exit`. A supplied admission receipt is schema/hash checked
and blocks only its failed role; it cannot suppress planned rows. Add
`cross-harness-execute` to the packaged umbrella dispatcher in
`harness.cli_entry`; do not rely on checkout-only `scripts/` dispatch. The
script and `scripts/run_harness_cli.py` delegate to the same packaged main.

The command writes existing run-receipt and scorecard schemas plus
`artifact-index.json` and `comparison-input.json`. It does not mint the
closed-loop seed; the existing seed orchestrator retains ownership of that
schema in Task 7. The comparison input is exactly
`{"schema":"harness.cross-harness-task-scorecard/v1","rows":[...]}`.
Compatibility tests feed the scorecard directly into the existing comparison
consumer and prove the seed builder can retain its paths in Task 7.

At local-phase start, recheck the endpoint gate with an injected current time,
the exact gate run ID, and `max_gate_age_seconds=900`. If it is stale, every
planned local row is emitted unavailable without launching the adapter. Each
unavailable local row must project sanitized `role`, `backend`, requested and
observed model references, endpoint profile ID/hash, attempted gate path/hash
and run ID, blocking gate code, and failure reason from runtime/gate evidence.
Tests assert these fields on all eight blocked local rows and reject secret or
raw-header fields.

- [ ] **Step 6: Run tests, file gate, and commit**

```text
python -m pytest tests/test_cross_harness_adapters.py tests/test_cross_harness_executor.py tests/test_harness_cli.py tests/test_cli_launch.py -q
python scripts/check_file_gate.py
git add harness/cross_harness_adapters.py harness/cross_harness_cli.py harness/cli_entry.py scripts/run_cross_harness_execution.py scripts/run_harness_cli.py tests/test_cross_harness_adapters.py tests/test_harness_cli.py tests/test_cli_launch.py
git commit -m "feat: expose cross-harness execution adapters"
```

### Task 7: Feed executed rows through existing synthesis and topology

**Files:**
- Create: `harness/cross_harness_seed_steps.py`
- Create: `tests/test_cross_harness_seed_steps.py`
- Modify: `scripts/run_closed_loop_benchmark_seed.py`
- Modify: `tests/test_closed_loop_benchmark_seed.py`
- Modify: `scripts/run_benchmark_profile_manifest.py`
- Modify: `scripts/run_benchmark_profile_coverage.py`
- Modify: `scripts/run_benchmark_execution_matrix.py`
- Modify: `scripts/run_harness_comparison_report.py`
- Modify: `scripts/run_closed_loop_outcome_report.py`
- Modify: `harness/schematic_drift.py`
- Create: `scripts/run_cross_harness_integration_map.py`
- Create: `tests/test_cross_harness_integration_map.py`
- Modify: `project-docs/schematics/closed-loop-integration.graph.json`
- Modify: `scripts/run_schematic_drift_check.py`
- Modify: corresponding existing tests.

**Interfaces:**
- Consumes: existing scorecard rows and run receipts from Task 6.
- Produces: seed-owned admission/Spark/local orchestration, scoped coverage,
  Spark-only comparison, separate local signals, process outcome, and refreshed
  executor topology plus a runtime integration map.

- [ ] **Step 1: Write consumer RED tests before production edits**

Prove profile scope is four tasks, repeated attempts do not inflate the eight
Spark provider-unit coverage denominator, unavailable rows remain visible but
metric-incomplete, oracle failures enter quality, drift/unverifiable rows do
not, latency uses median/range with `n`, comparison rejects hash mismatch,
every cohort reports planned/admitted/blocked/launched, distinct enforcement
hashes survive synthesis, the Spark comparison is labeled
policy-non-equivalent, Spark/local denominators remain 24/8, and no 84-run
command is executable. Prove the seed builder owns one ordered
`cross_harness_admission`, `cross_harness_local`, and `cross_harness_spark`
step sequence, each local phase rechecks gate freshness before launch, each
result retains its expected `run.json` and
`comparison-input.json`, and later phases consume the admission receipt.
Test that the integration map requires and hashes lane-before/lane-after, auth,
profiles, endpoint gate, runtime matrix, seed, coverage, comparison, and outcome
artifacts; preserves each observed schema/status; and is written before drift.

- [ ] **Step 2: Run the focused consumer tests and record RED**

```text
python -m pytest tests/test_cross_harness_seed_steps.py tests/test_closed_loop_benchmark_seed.py tests/test_benchmark_profile_manifest.py tests/test_benchmark_profile_coverage.py tests/test_benchmark_execution_matrix.py tests/test_harness_comparison_report.py tests/test_closed_loop_outcome_report.py tests/test_cross_harness_integration_map.py tests/test_schematic_drift_check.py -q
```

- [ ] **Step 3: Extend existing consumers without a result schema**

Use separate denominators:

```text
availability = planned, admitted, blocked, launched
execution reliability = well-formed returned / launched
deterministic quality = oracle pass / (oracle pass + oracle fail)
latency/resources = well-formed returned rows, with included states and n
```

Only verified, well-formed pass/fail rows enter deterministic quality. Keep
legacy fields for older inputs. Never coerce null usage or latency to zero.
Carry the common declared-policy hash and each adapter's actual-enforcement hash
as separate fields. Matching declared-policy hashes never imply control
equivalence; render the baseline as an orchestration-stack comparison with
`policy_equivalence=non_equivalent` unless effective controls were independently
proved equal.

Keep `harness.closed-loop-benchmark-seed/v1` owned by
`scripts/run_closed_loop_benchmark_seed.py`. Put construction of the three
cross-harness `OrchestrationStep` objects in the new sub-300-line
`harness/cross_harness_seed_steps.py`; the executor never emits a seed. Add a
focused `--cross-harness-only` seed mode plus manifest, runtime-matrix,
endpoint-gate, gate-run-ID, source-root, and source-commit inputs. The ordered
steps call the packaged executor for admission, local, and Spark phases in that
order so local freshness is checked before the long Spark pilot. Local and
Spark receive the admission receipt and turn any failed role into planned typed
unavailable rows. An expired local gate blocks the eight rows; it does not
trigger an automatic re-gate or retry. Extend generic step receipts with UTC `started_at` and
`finished_at`, exit code, stdout/stderr SHA-256, and redacted environment-name
inventory so the seed is also the live command ledger. The parent seed result
lists every child result and all phase artifact paths.

- [ ] **Step 4: Refresh execution order and integration topology**

Place cross-harness execution after auth/endpoint gates and before coverage and
comparison. Pass only Spark scorecards to the Spark comparison. Add the executor
node, required file, and edges from manifest/runtime/gates to executor and from
executor to coverage/comparison/seed. Replace archived default paths with
repository-relative defaults. Add `--benchmark-ids` to the profile command so
the live deck selects only `cross_harness_reproducibility_matrix`; reject
unknown IDs and prove the scoped profile contains exactly the four pilot units.
Add a zero-dependency integration-map writer that consumes only generated
artifact metadata and hashes. It emits
`harness.cross-harness-integration-map/v1` JSON plus Markdown, separates
observed/inferred/blocked/unknown state, and does not infer live status from the
static graph. Run this writer after outcome and before schematic drift; drift's
`--report` input is the generated Markdown, never a missing future path.

- [ ] **Step 5: Run consumer suites and enforce net-zero frozen files**

Run the Step 2 command again, followed by `python scripts/check_file_gate.py`.
Shrink local helpers or prose before adding lines to grandfathered files.

- [ ] **Step 6: Commit**

```text
git add harness/cross_harness_seed_steps.py scripts/run_closed_loop_benchmark_seed.py tests/test_cross_harness_seed_steps.py tests/test_closed_loop_benchmark_seed.py scripts/run_benchmark_profile_manifest.py scripts/run_benchmark_profile_coverage.py scripts/run_benchmark_execution_matrix.py scripts/run_harness_comparison_report.py scripts/run_closed_loop_outcome_report.py scripts/run_cross_harness_integration_map.py tests/test_cross_harness_integration_map.py harness/schematic_drift.py project-docs/schematics/closed-loop-integration.graph.json scripts/run_schematic_drift_check.py tests/test_benchmark_profile_manifest.py tests/test_benchmark_profile_coverage.py tests/test_benchmark_execution_matrix.py tests/test_harness_comparison_report.py tests/test_closed_loop_outcome_report.py tests/test_schematic_drift_check.py
git commit -m "feat: report cross-harness execution outcomes"
```

### Task 8: Run offline end-to-end verification

**Files:**
- Modify only if a failing test proves a scoped defect in Tasks 1-7.
- Write command receipts under the external experiment root.

**Interfaces:**
- Produces a fully offline dry fixture with exact 24 and eight-row matrices.

- [ ] **Step 1: Run focused lane and execution suites**

```text
python -m pytest tests/test_mcp_client.py tests/test_lanes.py tests/test_cli_launch.py -q
python -m pytest tests/test_adapter_runtime_matrix.py tests/test_cross_harness_manifest.py tests/test_cross_harness_executor.py tests/test_cross_harness_adapters.py tests/test_cross_harness_oracles.py tests/test_benchmark_execution_matrix.py tests/test_harness_comparison_report.py tests/test_benchmark_profile_coverage.py tests/test_closed_loop_outcome_report.py -q
```

- [ ] **Step 2: Run full repository gates**

```text
python -m pytest tests/ -q
python scripts/check_file_gate.py
python scripts/check_verifier_stdlib.py
python scripts/check_claim_language.py
python scripts/check_public_instructions.py
git diff --check
```

Run `python -m harness.cli_entry gate` in a disposable worktree because it
rewrites the tracked gate artifact with a machine path. Capture its output and
discard only that disposable worktree.

- [ ] **Step 3: Assert offline artifact invariants**

Check exact tuple uniqueness, 24 Spark rows, eight local rows, matching prompt,
input and tool-policy hashes, receipt rechecks, quality numerator bounds,
latency `n`, all four availability counts (`planned`, `admitted`, `blocked`,
`launched`), no local rows in the Spark comparison, isolated per-attempt
workspaces, matching pre/post source-tree snapshots, and no 84-run command.

- [ ] **Step 4: Commit only necessary defect fixes**

If no defect surfaced, make no code commit for this task. Record every command,
exit code, time interval, stdout/stderr hash, and does-not-prove statement in the
external experiment command ledger.

### Task 9: Execute fresh admission, pilot, local baseline, and reports

**Files:**
- Write: external `experiments/2026-08-11-truth-first-benchmark/`
- Create: external methodology, comparison, integration-map, experimental
  outcome, and next-loop reports.

**Interfaces:**
- Consumes: the clean, reviewed Flywheel branch and existing endpoint profiles.
- Produces: fresh lane, auth, endpoint, attempt, receipt, synthesis, and report
  evidence. Does not deploy, publish, or send outreach.

Before execution, write `commands/run-context.json` with the fully resolved
Python executable, repository root, external artifact root, source commit,
run ID, local model base root, model references, and backend. The base root is
recorded only in the private external context, never a public artifact.
Write `commands/live-command-deck.json` as argv arrays with no unresolved
placeholder. Each entry includes command ID, cwd, allowed environment-variable
names, expected outputs and schemas, strict-exit policy, and allowed follow-up
when nonzero. Seal both files with SHA-256 before the first live command. The
templates below become exact only after substitution from the sealed context:
The admission, Spark, and local arrays are expected child commands generated by
the seed builder and are not invoked a second time by the operator.

```text
lane-before-presence: python -c "import json; from harness.lanes import lane_roster; print(json.dumps(lane_roster(probe=False), sort_keys=True))"
lane-before-probe:    python -c "import json; from harness.lanes import lane_roster; print(json.dumps(lane_roster(probe=True), sort_keys=True))"
lane-after-presence:  python -c "import json; from harness.lanes import lane_roster; print(json.dumps(lane_roster(probe=False), sort_keys=True))"
lane-after-probe:     python -c "import json; from harness.lanes import lane_roster; print(json.dumps(lane_roster(probe=True), sort_keys=True))"

manifest: python scripts/run_cross_harness_manifest.py
  --task-set benchmarks/agentic-task-set-v1.json
  --contract benchmarks/cross-harness-adapter-contract-v1.json
  --provider-roles codex_harness,flywheel_harness,local_14b,local_32b
  --artifact-dir ${ROOT}/manifests --out ${ROOT}/manifests/manifest.json
  --markdown-out ${ROOT}/manifests/manifest.md --store-root ${ROOT}/store
  --run-id ${RUN_ID}-manifest

endpoint-auth: python scripts/run_endpoint_auth_status.py
  --require codex_subscription --out ${ROOT}/gates/auth.json
  --markdown-out ${ROOT}/gates/auth.md --store-root ${ROOT}/store
  --run-id ${RUN_ID}-auth

endpoint-profiles: python scripts/run_model_endpoint_profiles.py
  --models 14B,32B --base-root ${MODEL_BASE_ROOT}
  --out ${ROOT}/gates/profiles.json
  --markdown-out ${ROOT}/gates/profiles.md --store-root ${ROOT}/store
  --run-id ${RUN_ID}-profiles

endpoint-gate: python scripts/run_model_endpoint_gate.py
  --profile-artifact ${ROOT}/gates/profiles.json --models 14B,32B
  --backends ${LOCAL_BACKENDS} --prompt "Return exactly READY."
  --timeout-seconds 300 --max-tokens 64 --seed 7
  --out ${ROOT}/gates/endpoint.json --markdown-out ${ROOT}/gates/endpoint.md
  --store-root ${ROOT}/store --run-id ${RUN_ID}-endpoint --strict-exit

runtime-matrix: python scripts/run_adapter_runtime_matrix.py
  --contract benchmarks/cross-harness-adapter-contract-v1.json
  --endpoint-profiles ${ROOT}/gates/profiles.json
  --endpoint-auth-status ${ROOT}/gates/auth.json
  --endpoint-gate ${ROOT}/gates/endpoint.json
  --expected-gate-run-id ${RUN_ID}-endpoint --max-gate-age-seconds 900
  --out ${ROOT}/gates/runtime-matrix.json
  --markdown-out ${ROOT}/gates/runtime-matrix.md
  --store-root ${ROOT}/store --run-id ${RUN_ID}-runtime

seed-child-admission: python -m harness.cli_entry cross-harness-execute
  --manifest ${ROOT}/manifests/manifest.json
  --runtime-matrix ${ROOT}/gates/runtime-matrix.json
  --artifact-root ${ROOT}/admission-smoke --phase admission-smoke
  --tasks agt-001,agt-003
  --roles codex_harness,flywheel_harness,local_14b,local_32b
  --repetitions 1 --run-id ${RUN_ID}-admission
  --source-commit ${COMMIT} --source-root ${REPO}
  --timeout-seconds 300 --cache-state cold_declared
  --endpoint-gate ${ROOT}/gates/endpoint.json
  --gate-run-id ${RUN_ID}-endpoint --max-gate-age-seconds 900 --strict-exit

seed-child-local: python -m harness.cli_entry cross-harness-execute
  --manifest ${ROOT}/manifests/manifest.json
  --runtime-matrix ${ROOT}/gates/runtime-matrix.json
  --artifact-root ${ROOT}/local-baseline --phase local
  --tasks agt-001,agt-003,agt-009,agt-010
  --roles local_14b,local_32b --repetitions 1
  --run-id ${RUN_ID}-local --source-commit ${COMMIT} --source-root ${REPO}
  --admission-receipt ${ROOT}/admission-smoke/run.json
  --timeout-seconds 300 --cache-state cold_declared
  --endpoint-gate ${ROOT}/gates/endpoint.json
  --gate-run-id ${RUN_ID}-endpoint --max-gate-age-seconds 900 --strict-exit

seed-child-spark: python -m harness.cli_entry cross-harness-execute
  --manifest ${ROOT}/manifests/manifest.json
  --runtime-matrix ${ROOT}/gates/runtime-matrix.json
  --artifact-root ${ROOT}/spark-pilot --phase spark
  --tasks agt-001,agt-003,agt-009,agt-010
  --roles codex_harness,flywheel_harness --repetitions 3
  --run-id ${RUN_ID}-spark --source-commit ${COMMIT} --source-root ${REPO}
  --admission-receipt ${ROOT}/admission-smoke/run.json
  --timeout-seconds 300 --cache-state cold_declared --strict-exit

seed: python scripts/run_closed_loop_benchmark_seed.py
  --cross-harness-only --cross-harness-manifest ${ROOT}/manifests/manifest.json
  --cross-harness-runtime-matrix ${ROOT}/gates/runtime-matrix.json
  --cross-harness-endpoint-gate ${ROOT}/gates/endpoint.json
  --cross-harness-gate-run-id ${RUN_ID}-endpoint
  --cross-harness-max-gate-age-seconds 900
  --cross-harness-source-commit ${COMMIT}
  --cross-harness-source-root ${REPO}
  --cross-harness-attempt-timeout-seconds 300
  --benchmark-timeout-seconds 10800 --artifact-dir ${ROOT}
  --store-root ${ROOT}/store --out ${ROOT}/closed-loop-seed.json
  --run-title ${RUN_ID} --strict-exit

profile: python scripts/run_benchmark_profile_manifest.py
  --providers codex_harness,flywheel_harness,local_14b,local_32b
  --benchmark-ids cross_harness_reproducibility_matrix
  --artifact-roots ${ROOT}/spark-pilot;${ROOT}/local-baseline
  --max-artifacts 128 --out ${ROOT}/reports/profile.json
  --markdown-out ${ROOT}/reports/profile.md --store-root ${ROOT}/store
  --run-id ${RUN_ID}-profile

coverage: python scripts/run_benchmark_profile_coverage.py
  --profile ${ROOT}/reports/profile.json
  --artifacts ${ROOT}/spark-pilot/comparison-input.json;${ROOT}/local-baseline/comparison-input.json
  --out ${ROOT}/reports/coverage.json
  --markdown-out ${ROOT}/reports/coverage.md --store-root ${ROOT}/store
  --run-id ${RUN_ID}-coverage

comparison: python scripts/run_harness_comparison_report.py
  --artifacts ${ROOT}/spark-pilot/comparison-input.json
  --flywheel-role flywheel_harness --codex-role codex_harness
  --out ${ROOT}/reports/spark-comparison.json
  --markdown-out ${ROOT}/reports/spark-comparison.md
  --store-root ${ROOT}/store --run-id ${RUN_ID}-comparison

outcome: python scripts/run_closed_loop_outcome_report.py
  --input ${ROOT}/closed-loop-seed.json
  --out ${ROOT}/reports/outcome.json
  --markdown-out ${ROOT}/reports/outcome.md
  --store-root ${ROOT}/store --run-id ${RUN_ID}-outcome

execution-matrix: python scripts/run_benchmark_execution_matrix.py
  --providers codex_harness,flywheel_harness,local_14b,local_32b
  --run-id ${RUN_ID}-matrix --artifact-dir ${ROOT}/matrix
  --store-root ${ROOT}/store --out ${ROOT}/reports/execution-matrix.json
  --markdown-out ${ROOT}/reports/execution-matrix.md

integration-map: python scripts/run_cross_harness_integration_map.py
  --graph project-docs/schematics/closed-loop-integration.graph.json
  --lane-before ${ROOT}/lane-truth/before-live.json
  --lane-after ${ROOT}/lane-truth/after-live.json
  --auth ${ROOT}/gates/auth.json --endpoint-profiles ${ROOT}/gates/profiles.json
  --endpoint-gate ${ROOT}/gates/endpoint.json
  --runtime-matrix ${ROOT}/gates/runtime-matrix.json
  --seed ${ROOT}/closed-loop-seed.json --coverage ${ROOT}/reports/coverage.json
  --comparison ${ROOT}/reports/spark-comparison.json
  --outcome ${ROOT}/reports/outcome.json
  --out ${ROOT}/reports/integration-map.json
  --markdown-out ${ROOT}/reports/integration-map.md
  --store-root ${ROOT}/store --run-id ${RUN_ID}-integration-map

schematic-drift: python scripts/run_schematic_drift_check.py
  --graph project-docs/schematics/closed-loop-integration.graph.json
  --report ${ROOT}/reports/integration-map.md
  --out ${ROOT}/reports/schematic-drift.json
  --markdown-out ${ROOT}/reports/schematic-drift.md
  --store-root ${ROOT}/store --run-id ${RUN_ID}-drift
```

Coverage takes both phase scorecards; comparison takes only the Spark scorecard;
outcome takes the one seed-builder-owned orchestration receipt and reports the
Spark and local cohorts separately. Every `--strict-exit` nonzero is ledgered
and may only trigger typed blocked rows or later synthesis; it never authorizes
an unplanned retry.

Only the top-level `seed` command launches benchmark phases. The three
`seed-child-*` arrays are sealed expected `planned_steps` values and are
executed exactly once by the seed builder. The operator and command-deck runner
must reject any attempt to invoke them separately; tests assert one admission,
one Spark, and one local child result and exact 24/8 planned row counts.

The sealed deck marks all four lane entries as JSON-stdout captures. Its runner
writes stdout to a same-directory temporary file, requires
`schema="flywheel.lanes/v1"`, fsyncs, atomically renames to
`lane-truth/before-presence.json`, `before-live.json`,
`after-presence.json`, or `after-live.json`, and records the final SHA-256.
Before entries run in the disposable `d164aa8` worktree; after entries run in
the reviewed branch. Stderr remains only in the command ledger and is never
concatenated into the JSON artifact.

The sealed deck asserts schemas before hashing outputs: auth
`harness.endpoint-auth-status/v1`; profiles
`harness.model-endpoint-profiles/v1`; endpoint gate
`harness.model-endpoint-gate/v1`; runtime matrix
`harness.adapter-runtime-matrix/v1`; manifest
`harness.cross-harness-manifest/v1`; phase comparison inputs
`harness.cross-harness-task-scorecard/v1`; phase run receipts
`harness.cross-harness-run-receipt/v1`; phase seeds
`harness.closed-loop-benchmark-seed/v1`; profile
`harness.benchmark-profile-manifest/v1`; coverage
`harness.benchmark-profile-coverage/v1`; comparison
`harness.comparison-report/v1`; outcomes `harness.closed-loop-outcome/v1`;
execution matrix `harness.benchmark-execution-matrix/v1`; and drift
`harness.schematic-drift-check/v1`. The integration map must match
`harness.cross-harness-integration-map/v1`. A missing or mismatched schema
blocks that consumer and remains in the ledger.

- [ ] **Step 0: Freeze the live contract and true pre-repair baseline**

Copy the exact admitted task-set and adapter-contract JSON into the external
experiment root and record their SHA-256 values in the artifact index. In a
disposable worktree at base commit `d164aa8`, capture both the presence-only and
live-probed lane rosters before any repair. Record every command in the live
command ledger with start time, end time, exit code, stdout/stderr hashes,
redacted environment-variable-name inventory, and a does-not-prove statement.
Remove the disposable worktree only after its evidence is indexed.

- [ ] **Step 1: Capture environment and post-repair lane truth**

Record source commit, branch, dirty-state boundary, tool versions, non-secret
environment variable names, post-repair presence-only roster, post-repair
live-probed roster, and exact failure details. Compare these with the base-commit
rosters from Step 0. Confirm no `public/public` path appears. Apply the complete
command-ledger fields from Step 0 to every live command in Steps 1-7.

- [ ] **Step 2: Generate fresh auth, endpoint-profile, and endpoint-gate rows**

Use seed 7, maximum 64 generation tokens, and a 300-second endpoint timeout.
Record exact model reference, backend, profile hash, and Ollama digest when
available. Do not start an absent service.

- [ ] **Step 3: Run admission smoke separately**

Run `agt-001` and `agt-003` once for every statically reachable role. Prove
adapter launch, live authorization, artifact shape, oracle, receipt recheck, and
comparison-key agreement. A failure blocks that role's live execution and
becomes typed unavailable evidence.

- [ ] **Step 4: Run or block the eight-row local baseline**

Use `local_14b,local_32b`, the same four selectors, and one repetition. Create
all eight rows. Label this descriptive because one repetition cannot establish
comparative reliability. Recheck the 900-second gate freshness at phase start;
expired evidence blocks all eight rows without re-gating automatically.

- [ ] **Step 5: Run or block the 24-row Spark pilot**

Use `codex_harness,flywheel_harness`, four selectors, and three repetitions.
Create all 24 rows even when a role is unavailable.

- [ ] **Step 6: Generate synthesis, integration map, then drift outputs**

Report Spark and local denominators separately. Include task completion,
deterministic quality, tool success, latency median/range, cost/resource values
or explicit null reasons, reliability, failure modes, receipt verification, and
reproducibility. State that the Spark result compares orchestration stacks, not
a pure one-variable harness ablation. Report `planned`, `admitted`, `blocked`,
and `launched` for both cohorts.

Run profile, coverage, Spark comparison, outcome, and execution matrix first.
Then generate and schema/hash-check the integration-map JSON and Markdown. Only
after that succeeds, run schematic drift against the generated Markdown. A
missing map is a blocked drift observation, never empty report text.

- [ ] **Step 7: Write durable external reports and next-loop decision**

Separate observation, inference, unknown, and blocked state. Link raw artifacts,
name limitations, refresh the integration map, and select the next integration
wedge from evidence. Stop before the 84-attempt expansion regardless of pilot
result in this plan.

### Task 10: Independent review and branch handoff

**Files:**
- Review the complete Flywheel branch and external experiment artifacts.

**Interfaces:**
- Produces: specification verdict, code-quality verdict, evidence/calculation
  verdict, and a final branch disposition.

- [ ] **Step 1: Generate the whole-branch review package**

Use the branch merge base, never `HEAD~1`. Include commit list, diff stat, full
diff, task reports, deferred findings, and external artifact index.

- [ ] **Step 2: Request independent code and evidence review**

The reviewer checks every approved requirement, denominator calculation,
receipt recheck, path/secret scan, row count, comparison key, local/Spark split,
isolated attempt workspaces, pre/post source-tree integrity, frozen live
contract hashes, command-ledger completeness, true base-commit lane evidence,
and stop-before-84 rule.

- [ ] **Step 3: Remediate one consolidated final finding wave**

Use one fixer for the full finding set, rerun covering tests, and request one
scoped re-review. Do not dismiss load-bearing findings.

- [ ] **Step 4: Re-run terminal verification and present branch options**

Only claim completion after fresh terminal output confirms the full suite,
repository gates, artifact invariants, clean reviewed scope, and external report
hashes. Then use `superpowers:finishing-a-development-branch` for the handoff.
