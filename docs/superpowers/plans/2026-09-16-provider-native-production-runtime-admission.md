# Provider Native Production Runtime Admission Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Use `superpowers:test-driven-development` before changing production code for each task.

**Goal:** Admit provider-native Codex and Claude sessions into the existing GatewayOperations, grant, Journey and AgentTrace path with a production runtime registry, without trusting caller-supplied config digests, reading provider credentials, or replaying ambiguous provider side effects.

**Architecture:** Keep the current provider-session turn/resume/reconcile operations as dispatch. Add runtime admission that produces gateway-derived provider binding snapshots, freezes them into one-use grant records, constructs adapters only from a reviewed registry after authorization, and exposes separate live approval custody for provider tool requests. Empty or unsupported runtime registry entries keep execution disabled.

**Tech stack:** Python gateway/harness modules, existing Journey lifecycle and grant store, existing Codex app-server client, existing Claude SDK stdio client, focused pytest fixtures first.

**Spec:** `docs/superpowers/specs/2026-09-16-provider-native-sessions-design.md`; Task 2 in `docs/superpowers/plans/2026-09-16-provider-native-sessions.md`; AgentView gap in `docs/superpowers/plans/2026-09-16-provider-native-sessions-agentview-integration.md`.

## Current source evidence

- Provider actions and paths already exist: `harness/provider_session_gateway_fields.py:4-13`, `harness/provider_session_gateway_fields.py:27-32`; current provider scope is only `network` in `harness/provider_session_operation_shape.py:41-42`.
- The adapter seam requires `current_binding`, `start_turn`, `resume` and `reconcile`: `harness/provider_session_contract.py:24-35`, `harness/provider_session_contract.py:114-117`.
- Provider routes already use GatewayOperations, but only pass a raw fake adapter map and optional resolver: `harness/gateway_operation_route.py:268-278`.
- Missing adapter behavior is honest: `harness/provider_session_runner.py:121-130` returns `runtime_execution_disabled=True`, `side_effect_status=none` and indeterminate history.
- Dispatch intent is write-ahead before adapter calls, and binding drift checks provider/workspace/config/capability: `harness/provider_session_runner.py:140-154`, `harness/provider_session_runner.py:242-253`.
- Provider approvals deny by default and require exact identity plus shaped allow/deny data: `harness/provider_session_runner.py:211-239`.
- Reconcile proof depends on explicit dispositions and structured provider observation, not a positive string alone: `harness/provider_session_source.py:16-22`, `harness/provider_session_source.py:148-151`, `harness/provider_session_source.py:213-216`.
- Existing grant binding supports only `agent.run`: `harness/gateway_provider_adapter.py:22-36`, `harness/gateway_agent_grant.py:7-10`, `harness/gateway_grant_summary.py:22-25`.
- The grant route freezes before proposal and before consume, compares saved records, then consumes a one-use grant: `harness/gateway_grant_route.py:104-121`, `harness/gateway_grant_route.py:190-220`.
- GatewayOperations preserves idempotency by comparing queued payloads before spawning work: `harness/gateway_operations.py:58-78`.
- Operation reads exist at `/api/operations` and `/api/operations/{ref}/{events,result,trace}`: `harness/gateway_operation_read_dispatch.py:5-30`; no provider runtime binding/capability read surface exists for AgentView.
- AgentView planning already requires pending provider approvals to remain display-only until backend approval custody exists: `docs/superpowers/plans/2026-09-16-provider-native-sessions-agentview-integration.md:345-347`.
- Codex direct CLI is held because project config isolation is unadmitted: `docs/superpowers/specs/2026-09-16-provider-native-sessions-design.md:20-29`, `docs/native-cli-session-contract.md:7-15`.
- The spec requires effective config enforcement, correlated approvals, recovery reconciliation and no secret leakage: `docs/superpowers/specs/2026-09-16-provider-native-sessions-design.md:80-91`.
- Verification must move from deterministic fixtures to no-generation installed-runtime compatibility, then authorized synthetic session: `docs/superpowers/specs/2026-09-16-provider-native-sessions-design.md:93-102`.
- Current CLI custody keeps account auth directories provider-owned and avoids reading/copying credentials: `docs/native-cli-session-contract.md:29-39`.
- Existing runtime helpers provide synthetic env, runtime/auth pinning and current Codex boundary refusal: `harness/gateway_cli_runtime.py:29-36`, `harness/gateway_cli_runtime.py:90-93`, `harness/gateway_cli_runtime.py:114-121`.
- Codex has typed `config/read(includeLayers)` and `configRequirements/read`: `harness/codex_session_client.py:101-109`.
- Claude SDK custody already requires injected launchers, initialize before input, manual permission mode and stdio permission prompt: `harness/claude_session_client.py:18-21`, `harness/claude_session_transport.py:45-48`, `harness/claude_session_contract.py:40-41`, `harness/claude_session_contract.py:105-127`.
- Claude provider session code is an injected-client adapter and does not prove launch/runtime admission; resume/reconcile is unsupported without history proof: `harness/claude_provider_session.py:3-5`, `harness/claude_provider_session.py:69-74`, `harness/claude_provider_session_shapes.py:225-228`.
- Existing false-success tests cover runtime disabled, stale config, replay, approval denial, disconnect-after-effect, missing history, stale/cross-Journey proof, Codex approval/session mismatch and Claude terminal-without-history: `tests/test_provider_session_operation_bindings.py:71-118`, `tests/test_provider_session_idempotency.py:60-107`, `tests/test_provider_session_recovery.py:39-52`, `tests/test_provider_session_recovery.py:194-196`, `tests/test_provider_session_reconcile_proof.py:112-142`, `tests/test_codex_provider_session_review.py:35-37`, `tests/test_codex_provider_session_review.py:219-221`, `tests/test_claude_provider_session.py:16-18`, `tests/test_claude_provider_session.py:104-106`.

## Admission rules

- The gateway computes `workspace_ref`, `config_digest`, `capability_digest` and `provider_binding_ref`; AgentView copies returned values and must not ask the user to paste a digest.
- Caller-chosen unknown native IDs, mismatched digests, failed or indeterminate source operations, and unreconciled non-new turns are refused before provider input.
- `permission_scope` is the maximum turn envelope. It never auto-approves a live native tool request.
- A live provider approval is a separate exact decision over one native request identity, provider session identity, Journey operation, payload hash and response client id.
- Config isolation means active enforcement. Hashing provider-reported config is insufficient unless uncontrolled layers, hooks, MCP servers, plugins, apps, rules files and workspace project config are absent or bounded by policy.
- Codex direct CLI remains unavailable until a documented project-config disable control or reviewed sealed-workspace design exists. Codex app-server admission requires enough `config/read(includeLayers=True)` and `configRequirements/read` evidence to enforce the boundary.
- Claude persistent sessions use manual SDK stdio permission custody; the one-shot `dontAsk` profile is not a production persistent-session policy.
- Cancellation remains honest: unproved native interruption or cancellation stays indeterminate and routes to reconcile.

## Unsupported cases to keep explicit

- Codex direct CLI production sessions while project config isolation is unadmitted.
- Codex app-server sessions when config layer provenance is missing, unknown or uncontrolled.
- Claude sessions when managed policy hooks or project settings cannot be isolated or positively bounded. If administrator-managed hooks may still run, the binding snapshot must state that limitation.
- Claude native history resume/reconcile until structured native history observation can bind source status.
- Gateway restart during a pending live provider approval. It cannot become allow; it closes or recovers as deny or indeterminate depending on send state.
- Provider account availability from executable presence, schema presence or binding read. Admission requires staged no-generation and authorized synthetic gates.

---

### Task 1: Add runtime binding snapshots and a discoverable read surface

**Files:** Create `harness/provider_session_runtime_binding.py`; modify `harness/gateway_operation_route.py`; modify `harness/gateway.py` only if the operation route needs a narrow mount; test `tests/test_provider_session_runtime_binding.py` and `tests/test_provider_session_binding_route.py`.

**API shape:**

```python
@dataclass(frozen=True)
class ProviderRuntimeBindingSnapshot:
    schema: str; provider: str; owner_ref: str; journey_ref: str
    workspace_ref: str; model: str; permission_scope_sha256: str
    config_digest: str; capability_digest: str; provider_binding_ref: str
    admitted: bool; reason: str; limitations: tuple[str, ...]
    runtime_kind: str; observed_at_event_head: str
```

`POST /api/provider-sessions/binding` takes `schema`, `journey_ref`, `expected_event_head`, `provider`, `workspace_ref`, optional `model`, optional `permission_scope` and optional `tool_policy_ref`. It returns the redacted snapshot plus `provider`, `workspace_ref`, `config_digest`, `capability_digest`, `provider_binding_ref` and `permission_scope` for the later one-use grant request.

- [ ] Write failing route tests proving AgentView fetches digests from the gateway and caller-supplied digests are ignored.
- [ ] Validate owner, Journey and event head with `JourneyStore`.
- [ ] Return `admitted=False` and reason `AGENT_NATIVE_RUNTIME_DISABLED` when the registry is empty.
- [ ] Return only redacted config facts and canonical digests; never account files, tokens, raw provider settings or credential paths.

### Task 2: Freeze provider binding into one-use grants

**Files:** Create `harness/provider_session_grant_binding.py`; modify `harness/gateway_provider_adapter.py`, `harness/gateway_agent_grant.py`, `harness/gateway_grant_summary.py`, `harness/gateway_grant_route.py`, `harness/provider_session_gateway_fields.py`, `harness/provider_session_operation_shape.py`; test `tests/test_provider_session_grant_binding.py` and `tests/test_provider_session_operation_bindings.py`.

**API shape:**

```python
def freeze_provider_session_binding(operation, *, owner_ref, journey_ref,
    expected_event_head, state_root, workspace_root=None, registry=None) -> FrozenJsonSnapshot | None: ...
def validate_provider_session_binding(record: dict, operation: dict, current: dict) -> None: ...
def review_provider_session_binding(record: dict) -> dict: ...
```

- [ ] Require `provider_binding_ref` for `turn`, `resume` and `reconcile` after Task 1 lands.
- [ ] Add `provider_session_binding` to `ExecutionPlan` beside `agent_binding`, only for `provider.session.*` actions.
- [ ] In prepare and authorize, recompute binding from the registry and reject mismatch in `provider_binding_ref`, workspace, config, capability, provider, model or permission-scope hash.
- [ ] Compare the saved snapshot before `GrantStore.consume`; drift fails without consuming the grant.
- [ ] Keep exact replay returning the existing operation snapshot and altered replay failing before provider input.
- [ ] Extend grant summaries with redacted provider binding review data.

### Task 3: Add production runtime registry and route it into grant plus dispatch

**Files:** Create `harness/provider_session_registry.py`; modify `harness/provider_session_runner.py`, `harness/gateway_operation_process.py`, `harness/gateway_operations.py`, `harness/gateway_operation_route.py`, `harness/gateway.py`; test `tests/test_provider_session_registry.py` and `tests/test_provider_session_operation_bindings.py`.

**API shape:**

```python
class ProviderSessionRuntimeRegistry(Protocol):
    def binding_snapshot(self, *, owner_ref: str, journey_ref: str,
        expected_event_head: str, operation: dict) -> dict: ...
    def adapter_for(self, *, authorized: AuthorizedOperation,
        operation_ref: str) -> ProviderSessionAdapter | None: ...
class EmptyProviderSessionRuntimeRegistry: ...
```

- [ ] Let `ProviderSessionProcessFactory` accept `registry=None`, preserving fake `adapters` only for tests.
- [ ] Resolve adapters inside `_execute` after authorization/source validation, with registry first and legacy fake map second.
- [ ] Pass the same registry through `GatewayOperations` and `GatewayOperationProcessFactory` so proposal, authorize and dispatch use one binding source.
- [ ] Keep default registry empty in `gateway.py` until runtime admission review accepts Codex and Claude bindings.
- [ ] Prove caller-supplied `config_digest` or `provider_binding_ref` cannot bypass the registry.

### Task 4: Add live provider approval broker and scoped routes

**Files:** Create `harness/provider_session_approval_broker.py` and `harness/provider_session_approval_route.py`; modify `harness/provider_session_runner.py`, `harness/gateway_operation_route.py`, `harness/gateway_operation.py`, `harness/provider_session_gateway_fields.py`; test `tests/test_provider_session_live_approvals.py` and `tests/test_provider_session_idempotency.py`.

**API shape:**

```python
@dataclass(frozen=True)
class PendingProviderApproval:
    operation_ref: str; owner_ref: str; journey_ref: str; request_identity: str
    provider: str; native_request_id: str; native_session_id: str
    native_thread_id: str; native_turn_id: str; tool: str; payload_sha256: str
    config_digest: str; capability_digest: str; state: Literal["pending", "answered", "expired"]
```

- [ ] Add `GET /api/provider-sessions/approvals?operation_ref=...` for pending facts in the current owner/Journey operation.
- [ ] Add separate grant action `provider.session.approval.respond` with `operation_ref`, `native_request_id`, `request_identity`, `decision`, optional `updated_input`, and `client_response_id`.
- [ ] Validate route shape: `allow` requires dict `updated_input`; `deny` must omit it.
- [ ] Publish `approval_requested` to AgentTrace, block the adapter callback for a bounded wait, then return a shaped decision or deny.
- [ ] Deny stale, cross-operation, cross-Journey, duplicate and payload-mismatched responses.
- [ ] Do not substitute a blanket no-tool profile for production approval custody. No-tool is only a policy option inside `permission_scope`.

### Task 5: Admit Codex app-server runtime through effective config enforcement

**Files:** Create `harness/codex_provider_session_runtime.py`; modify `harness/provider_session_registry.py`; modify `harness/codex_provider_session.py` only if the registry needs a small constructor hook or missing import repair after adapter review; test `tests/test_codex_provider_session_runtime.py`; extend `tests/test_codex_session_client.py`.

**API shape:**

```python
@dataclass(frozen=True)
class CodexEffectiveConfigSnapshot:
    workspace_ref: str; cwd: str; model: str; config_digest: str
    capability_digest: str; layers: tuple[dict, ...]
    requirements_digest: str; disabled_surfaces: tuple[str, ...]
    limitations: tuple[str, ...]
class CodexRuntimeAdmission: ...
```

- [ ] Write fake-client tests for `config/read(cwd=..., includeLayers=True)` and `configRequirements/read()` before any real Codex call.
- [ ] Reject missing layer provenance, unknown schema, uncontrolled user/project/workspace rules, enabled MCP, hooks, plugins, apps, web search/network outside policy, or model mismatch.
- [ ] Compute config digest from normalized enforced config plus layer identities; compute capability digest from admitted methods and approval/tool capabilities.
- [ ] Re-read effective config in `current_binding` before dispatch and compare to the grant-frozen snapshot.
- [ ] Bind Codex approval requests to method, request id, session/thread/turn, payload hash, config digest and Journey operation.
- [ ] Keep installed-runtime work behind a later no-generation config/schema gate, then authorized synthetic session acceptance.

### Task 6: Admit Claude persistent SDK runtime through launcher custody

**Files:** Create `harness/claude_provider_session_runtime.py`; modify `harness/claude_session_contract.py` only after the Claude adapter owner accepts a launcher-policy extension; modify `harness/provider_session_registry.py`; modify `harness/claude_provider_session.py` only if the registry needs a small constructor hook after adapter review; test `tests/test_claude_provider_session_runtime.py`; extend `tests/test_claude_session_protocol_prereqs.py`.

**API shape:**

```python
@dataclass(frozen=True)
class ClaudeManagedSessionPolicy:
    permission_mode: str = "manual"
    permission_prompt_tool_name: str = "stdio"
    strict_mcp_config: bool = True
    mcp_config: Mapping[str, Any] = field(default_factory=lambda: {"mcpServers": {}})
    settings: Mapping[str, Any] = field(default_factory=lambda: {"disableAllHooks": True})
    allowed_tools: tuple[str, ...] = (); disallowed_tools: tuple[str, ...] = ("mcp__*",)
class ClaudeRuntimeAdmission: ...
```

- [ ] Preserve `bypassPermissions` refusal and stdio permission-prompt requirements.
- [ ] Build clients only through the injected launcher, with `session_env`-style synthetic home and pinned account auth directory. Do not read or copy auth files.
- [ ] Use manual permission custody for persistent sessions; do not reuse one-shot `dontAsk`.
- [ ] Enforce config isolation by constructing argv/env/settings/MCP policy from reviewed inputs and rejecting unbounded provider-managed hooks or project settings. If admin hooks may run, state that limitation in the binding.
- [ ] Route Claude `can_use_tool` control requests through the live approval broker and prevent pending controls from leaking into the next turn.
- [ ] Keep Claude resume/reconcile unsupported until structured native history observation can bind source status.

### Task 7: Preserve recovery, cancellation and source-lineage invariants

**Files:** Modify `harness/provider_session_source.py` only if new binding fields must enter exact source proof checks; modify `harness/provider_session_recovery.py` and `harness/provider_session_runner.py`; test `tests/test_provider_session_recovery.py`, `tests/test_provider_session_reconcile_proof.py`, `tests/test_codex_provider_session_safety.py`, `tests/test_claude_provider_session.py`.

- [ ] Require `source_operation_ref` for non-new turns and verify owner, Journey, terminal source state, native identity, config digest, capability digest and current source head before dispatch.
- [ ] Keep write-ahead `dispatch_intent` before every adapter call.
- [ ] Treat missing history, partial history, log loss, EOF after input, transport write uncertainty and opaque provider errors as indeterminate.
- [ ] Only `native_terminal_observed` or structured `confirmed_not_applied` observations may unlock a non-new start turn.
- [ ] Preserve `close_indeterminate` and cancellation ambiguity when the provider cannot prove interrupt completion.
- [ ] Add regressions for stale config, grant replay, disconnect after effect, missing history, duplicate input, stale/cross-Journey/full-identity reconcile proof and live approval duplicate response.

## Review gates and commands

- Gate 1: root reviews this plan and freezes binding route, registry, grant binding and approval broker names.
- Gate 2 fake backend:

```powershell
python -m pytest tests/test_provider_session_runtime_binding.py tests/test_provider_session_binding_route.py tests/test_provider_session_grant_binding.py tests/test_provider_session_registry.py tests/test_provider_session_live_approvals.py tests/test_provider_session_operation_bindings.py tests/test_provider_session_idempotency.py -q
python scripts/check_file_gate.py
```

- Gate 3 fake Codex/Claude runtime admission:

```powershell
python -m pytest tests/test_codex_provider_session_runtime.py tests/test_codex_session_client.py tests/test_claude_provider_session_runtime.py tests/test_claude_session_protocol_prereqs.py -q
python scripts/check_file_gate.py
```

- Gate 4 recovery false-success suite:

```powershell
python -m pytest tests/test_provider_session_recovery.py tests/test_provider_session_reconcile_proof.py tests/test_codex_provider_session_safety.py tests/test_claude_provider_session.py -q
python scripts/check_file_gate.py
```

- Gate 5: after root approval, run no-generation runtime checks for Codex config/schema and Claude initialize/permission-prompt-tool custody.
- Gate 6: after Gate 5 review, run the authorized two-turn, bounded tool approval, interrupt, crash/restart and reconcile scenario. This is the first gate that can support a production runtime admission claim.

## Dependency sequence

1. Binding read route and provider binding snapshot.
2. Grant freeze/authorize binding comparison.
3. Registry injection into grant and dispatch.
4. Live approval pending/respond routes.
5. Codex fake effective-config admission.
6. Claude fake launcher-policy admission.
7. Recovery/cancel/source-lineage regression closure.
8. Installed no-generation compatibility.
9. Authorized synthetic runtime acceptance.

The first production seam to implement is Tasks 1-3. They make provider runtime identity gateway-derived, grant-frozen and dispatch-current without enabling real provider execution. Live approval routes come next because production tool workflows must be authorized per native request rather than disabled or auto-denied.
