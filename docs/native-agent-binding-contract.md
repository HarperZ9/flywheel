# Native agent execution binding

Supervised `agent.run` approvals freeze the model request, provider descriptor,
workspace and budgets before execution. This contract adds no subscription CLI
adapter and starts no service. It builds on the private trace contract.

The canonical operation accepts these optional fields. Missing fields remain
absent in canonical operation bytes; the plan resolves concrete defaults.

| Field | Accepted value | Frozen default |
| --- | --- | --- |
| `model` | `[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,159}` | Selected endpoint's configured model |
| `max_tokens` | Integer, 1 through 32768; booleans rejected | 1024 per request |
| `timeout_s` | Integer, 1 through 1800; booleans rejected | 300 seconds total |
| `max_steps` | Existing required integer, 1 through 12 | No implicit change |
| `root` | Existing optional workspace path | Gateway's configured workspace |
| `tool_protocol` | Optional `native` or `text` | Absent, which preserves v1 bytes |

No client base URL, environment, provider key or command is accepted. Supported
adapters are configured OpenAI-compatible providers, Anthropic and Gemini APIs,
and the synthetic stub. `serve`, its aliases, subscription CLIs and unknown
adapters return `AGENT_ENDPOINT_UNSUPPORTED`; they do not silently fall back.

`ExecutionPlan.agent_binding` is an immutable canonical-byte snapshot. Absent
`tool_protocol` still freezes schema `flywheel.gateway-agent-binding/v1` with
the original key set and bytes. Supplying `tool_protocol` freezes schema
`flywheel.gateway-agent-binding/v2`; `text` records the compatibility route and
`native` records a first-party native route. The binding digest joins the
execution-plan digest, which joins the exact grant request. It contains the
canonical operation digest;
provider name, adapter, configured URL, credential slot and specification digest;
explicit requested model or frozen default; optional catalog profile pins;
canonical workspace, filesystem identity and parent root policy; step, output and
wall budgets; write/execute/MCP capability gates; and transport constraints.
Native v2 additionally freezes `schema` as
`flywheel.gateway-agent-tool-protocol/v1`, `native_api_route`, the ToolExecutor
function schema digest, tool names, strict-schema requirement,
`parallel_tool_calls: false`, and `result_order_policy:
provider_order_sequential`.

Prepare and consume independently resolve the parent authority and compare the
whole snapshot before grant consumption or credential resolution. Changed model,
URL, default, profile pins, root identity or policy requires a new proposal.
An approved older agent proposal without the binding remains readable but returns
`AGENT_REPREPARE_REQUIRED` at consumption. Existing terminal and queued replay
uses its recorded plan digest and returns the existing operation; it never
redispatches against current configuration.

The owner-visible proposal summary adds `agent_execution`. Binding v1 keeps
review schema `flywheel.gateway-agent-review/v1`: `binding_sha256`, `endpoint`,
`base_url`,
`model`, `root`, `workspace_policy_sha256`, `budget`, and `capabilities`.
Binding v2 uses `flywheel.gateway-agent-review/v2` and adds the frozen
`tool_protocol` block.
`model` has `requested_model_reference` (nullable), `model_id`, `selection`
(`explicit` or `frozen_default`), `observation_policy`, and nullable `profile`.
Clients must include explicit selections in the operation and show this frozen
review before approval. This backend change does not supply the desktop selector.
For an older stored proposal without a binding, `agent_execution` is exactly
`{"status":"reprepare_required"}`; clients must offer preparation again instead
of treating that object as an executable review. The sanitized paired fixtures in
`tests/fixtures/native_agent_binding` contain synthetic Windows directory identity
values and can support client parser and review-sheet controls without a service.

The private worker protocol is v3 and requires the snapshot, its digest, and an
absolute monotonic deadline. The child verifies the original canonical operation
before materializing attachments, preserves `CredentialBindings.value_for`, and
constructs the adapter directly from the snapshot. It does not reread provider
defaults or `FLYWHEEL_WORKSPACE_ROOTS`. Workspace custody holds directory and
ancestor handles for the run on Windows. Production supervision requires a
Windows Job Object. POSIX validation is covered separately; this does not claim
that ordinary POSIX path-based tools resist a concurrent directory swap.

One owned-tree supervisor enforces the aggregate wall deadline, including tool
execution and blocked network setup. HTTP requests consume a shared attempt
budget no greater than `max_steps`, including provider errors and any existing
backend retry. There are no transport retries, redirects, ambient proxies, or
model fallbacks. Request bodies are at most 1 MiB and response bodies 2 MiB.
The token limit bounds the transmitted output request; it is not a promise that
the provider complies, nor a context-window limit. Frozen sampling records
`temperature: 0`, `router_seed: 0`, and `provider_seed: null`. The temperature
policy is `zero`, or `zero_or_omitted` for Anthropic's existing unsupported-value
retry. Native Anthropic freezes `temperature: null` with policy `omitted`, so the
first Messages request carries no sampling field. Transport rejects changed
sampling, unrequested provider seeds and
cross-provider headers. This does not claim provider-side deterministic sampling.
A nonstream response may
wait a further 30 seconds for terminal state commitment after execution stops.

Native OpenAI uses the Responses API with nonstreaming `store:false`, strict
function tools, exact `call_id` to `function_call_output` pairing, and stateless
replay of provider output items. Opaque reasoning or encrypted content blocks are
preserved as provider continuity material and are never decoded or converted into
tool intent. Native Anthropic uses Messages tool-use blocks, preserves assistant
content blocks in order, and appends an immediate user message containing all
`tool_result` blocks before any other user content. Duplicate, missing or replayed
IDs; loose tool schemas; malformed final responses; max-token or pause turns; and
refusals are typed failures before new tool side effects. Incidental text such as
`TOOL ...` inside a native response is not parsed or rescued.

The native tool schema is exactly the existing local `ToolGate` surface:
read/list/grep plus write tools only when `allow_write` is approved and `run` only
when `allow_exec` is approved. It carries no desktop, UIA, Relay, mobile,
hardware or administrator authority. Future workstation tools require a separate
reviewed capability profile that changes the frozen tool schema digest.

The owner-private ledger records each model call with binding digest, ordinal,
explicit request, frozen effective model, actual provider-reported model or null,
observation basis, elapsed milliseconds and reported usage. Raw native usage is
preserved when the shared normalizer cannot map it. Ollama's documented default
`:latest` tag normalization is the only local identity normalization. A reported
mismatch stops before tools. Missing observations remain unavailable; hosted
aliases remain provider-reported strings and are not rejected as mismatches.
Expected release artifact and manifest pins remain expectations. No model weight
or manifest observation is invented, and a matching name does not prove weights
or semantic correctness.

The full original request, source, tool results, thread and model observations
remain in the existing private trace. Public progress and terminal projections
retain the existing content-free shape and separately hashed trace references.
Credential values are excluded from both private records and public projections.
Closed failure reasons add `AGENT_BINDING_DRIFT`, `AGENT_REPREPARE_REQUIRED`,
`AGENT_MODEL_MISMATCH`, `AGENT_ENDPOINT_UNSUPPORTED`,
`AGENT_NATIVE_TOOL_UNSUPPORTED`, `AGENT_NATIVE_PROTOCOL_ERROR`,
`AGENT_NATIVE_INCOMPLETE`, `AGENT_NATIVE_REFUSAL` and
`OPERATION_DEADLINE_EXCEEDED`; deadline failure is distinct from user cancellation.

Focused controls cover parent-authority drift before consumption, changed private
IPC, root substitution before provider invocation, exact transmitted requests,
native observed aliases and unknowns, mismatch before tool use, source/credential
nonleak, terminal replay under changed configuration, and actual Windows owned
stub execution and deadline cleanup. Native focused controls add deterministic
fake-provider OpenAI and Anthropic two-turn execution, exact IDs and ordered
results, strict schema mismatch, unsupported native authority, incomplete or
malformed response handling, unchanged v1 compatibility, binding drift before
credential materialization, no native text rescue, redacted public projection and
exact native sampling. They do not establish live model quality, provider
availability, device acceptance, or launch readiness.
