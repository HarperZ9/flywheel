# Codex runtime configuration boundary

Root owns `harness/codex_provider_session_runtime.py` and its focused tests.
Backend registry/grant/broker ownership remains separate. Provider adapters stay
frozen during this increment. This refines production admission Task 5.

## Decision and evidence

Use a provider-owned, separately authenticated managed profile for a controlled
runtime. Do not copy tokens from an existing account. Existing shared account
configuration cannot be called isolated merely because session flags were passed.

An installed-runtime, no-generation probe on Codex 0.144.6 showed that passing
`mcp_servers={}` as a session override preserves inherited server entries. A new
server added to user config after initialization appeared on the next config read.
Session-flag project trust overrides also did not disable the already trusted
project layer in that experiment. These are observed counterexamples to the
proposed empty-table/flag isolation shortcuts, not complete execution experiments.

Official references: [configuration](https://learn.chatgpt.com/docs/config-file/config-reference)
and [app server](https://learn.chatgpt.com/docs/app-server).

## Increment

1. Add a strict, redacted config inspection result using the existing client.
   Require effective config, layer identities/versions and origins, and an explicit
   requirements response. Preserve the entire response in the private digest,
   including disabled layers; never return the raw settings or filesystem paths.
2. Refuse active project layers, unknown layer kinds, unmanaged enabled MCP,
   hooks/apps/plugins, unsupported model or sandbox/approval settings, and missing
   evidence. Missing or malformed config must not silently equal an empty config.
3. Separate `configuration_ready` from runtime admission. No config inspection
   alone may construct an executable production adapter or return `admitted=true`.
4. Use deterministic tests for the observed inherited-MCP counterexample, config
   drift, disabled-layer drift, malformed provenance, secret-bearing errors,
   and the positive explicit policy fixture before implementation.
5. Next integrate an owned launcher/profile lease with immutable reviewed policy,
   provider-owned login, fresh per-dispatch inspection, and actual no-generation
   compatibility. Then run authorized synthetic session/tool/restart acceptance.

## Policy of this first managed runtime

Explicit model, `read-only` sandbox, `on-request` approvals with user review,
disabled provider hooks/apps/plugins, no enabled external MCP, no web search.
Provider sandbox permission requests can still reach Flywheel's live broker;
this is not a blanket no-tool implementation. Broader scopes need distinct policy
and actual enforcement evidence. Native built-in read tools remain available.

The final launcher must enforce this policy across start/resume/turn, not only
observe it. Authentication, managed requirements, project trust and configuration
mutation require real-runtime tests before default registry activation. This
increment does not finish required native sessions or 1.0.0.

## Owned profile and launcher increment

Root owns new `harness/codex_managed_profile.py`, a small Windows file-lease helper
if needed, `harness/codex_managed_session.py` and corresponding focused tests.
A separate process-helper owner supplies persistent binary stdio with suspended
launch, Job Object custody and bounded tree cleanup. Reuse existing private
artifact roots and Windows file APIs rather than a second filesystem abstraction.

Create a dedicated profile below an explicit application state root, keyed by
owner and workspace identity. Its reviewed config marks the workspace untrusted
before launch. Profile configuration and executable bytes are pinned by file
handles for the session lifetime; never overwrite an existing different profile.
Authentication is provider-owned in this dedicated profile. No existing credential
file is opened or copied. Login wiring must use this profile and remain explicit.

Tests cover reproducible profile creation, conflicting existing configuration,
workspace/profile ancestor overlap, symlink/reparse rejection, environment secret
exclusion, executable/config mutation denial, and release of leases after cleanup.
The launcher forces explicit model and reviewed policy, inspects resolved layers
after initialize and before input, validates returned thread policy, and closes
the owned process on refusal. No config inspection alone registers an adapter.

This first boundary protects configuration against model workspace changes and
pins reviewed files. It does not claim to isolate a malicious administrator or
another trusted process that can create new machine-policy inputs. Unknown managed
constraints or policy drift refuse admission. Actual provider login, sandbox/tool
execution, restart history and cleanup acceptance precede production activation.
