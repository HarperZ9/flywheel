# Native CLI sessions in Gateway Operations

This adapter runs one official CLI session in the existing supervised
`agent.run` worker. The CLI owns its tool loop. It is not Flywheel's text
proposer loop and is not API-native `tool_protocol=native`.

Use `execution_mode: native_cli_session`, an explicit `model`, and endpoint
`claude-cli` or `codex-cli`. Do not supply `tool_protocol`, `max_tokens`,
`effort`, `test_cmd`, or API credential handles. Unsupported requests fail
before model execution. Source context and bounded continuation use the
existing operation and private trace paths. Continuation starts a fresh
session with selected context; it does not resume the provider conversation.

## Profiles and authority

| Profile | Model tools | Authority and limits |
| --- | --- | --- |
| `claude_restricted_files_v1` | Read, Glob, Grep; Edit and Write when granted | `--restricted` confines file tools to working directories. `--safe-mode` disables user customizations. `--tools` is explicit, MCP is denied, and unattended permission requests are denied. `allow_exec` is refused. Managed provider policy still applies. |
| `codex_windows_sandbox_v1` | Native commands; file changes when granted | Requires `allow_exec`. Uses read-only or workspace-write sandbox, explicitly unelevated Windows mode, no login shell, no network for workspace commands, no extra writable roots. Its OS read scope is broader than the working directory. Configured Flywheel root-only policies are refused. |

The gateway freezes exact argv digest, requested model, executable content
identity, observed CLI version/help digest, own-auth directory identity,
workspace identity/policy, tools and budget controls. The executable and
directory ancestors are held against replacement during execution.
No shell wrapper is accepted as native executable evidence.

Only `CLAUDE_CONFIG_DIR` or `CODEX_HOME` points at the existing official
client's auth directory. Flywheel does not read/copy account files, transport
tokens, log in, or mutate account configuration. HOME/USERPROFILE remain
the isolated worker profile. API keys and arbitrary parent environment do
not enter the CLI child. The CLI may update its own client state as part of
normal account operation. Executable presence does not prove signed-in status;
an unavailable account fails the session without provider fallback.

Codex ignores user configuration and rules. A `.codex` directory in the
working directory or its ancestors is refused, so unbound project settings
are not silently admitted. This is intentionally conservative. Provider
managed policies remain in force and are not bypassed. Claude's managed
policy can contain hooks that `--safe-mode` and session `disableAllHooks`
cannot disable. Those administrator-controlled startup effects are not
Flywheel model tool calls and have not been attested by the fixture tests.
Deployment review must resolve this authority before claiming a hooks-free
or fully confined process. No profile provides Windows elevation or UAC control.

## Budget and evidence contract

Grant review schema is `flywheel.gateway-agent-review/v3`. Existing root,
model, capability and budget fields remain, with `execution_mode` and
`cli_session`. `cli_session` includes provider, version, profile, tools,
filesystem_scope, auth_mode, controls and limitations. Synthetic paired
operation/binding/review fixtures live in `tests/fixtures/native_cli_session`.

Timeout is an owned-process deadline. Claude receives the requested
`max_steps` through its native `--max-turns` flag; successful terminal
metadata must report a turn count within that bound. Codex has no admitted
hard native turn limit; the review says `unsupported`. Neither profile
enforces a hard generation-token limit. Explicit `max_tokens` is refused,
and the review records `max_tokens: null`. Seed is unsupported, never echoed
as an applied setting. A requested model is forwarded exactly once; only
structured provider model metadata populates `model_observed`.

Private progress uses `cli_tool_call`, `cli_tool_result`, and `cli_message`
with the original provider source. Calls are not relabeled as Flywheel
ToolExecutor calls. Reasoning blocks, signatures, opaque continuation and
raw stderr are not retained. Unknown tool types, denied tools, malformed or
oversized JSON, nonzero exit, and missing successful terminal output fail.
Public progress contains only the existing owner/Journey trace locator.
Cancel, recovery and reopen use the same operation identity and supervisor.

## Verification and release boundary

Focused tests use deterministic CLI-shaped processes and real Windows job
ownership. They verify an artifact by independent readback, retain private
events/results, and prevent a delayed descendant write after deadline.
These tests do not establish provider sandbox enforcement, real account
readiness, Android connectivity, semantic task correctness or service quality.

Before release, the coordinated v3 grant parser and Rowan operation builder
must show these controls, omit unsupported fields, and preserve native trace
events. Run a separately authorized benign task through the installed Android
to desktop path using each admitted provider. Check its artifact, private
trace, cancellation, lost-response recovery and bounded continuation. Do not
substitute standalone CLI success for that acceptance.

Command execution for Claude, a narrower Codex read scope, managed-policy
attestation, and separately reviewed elevation profiles remain explicit next
steps toward workstation parity. The direct Claude-client to Relay MCP
workflow remains independent and is not removed or redirected by this adapter.

References: [Claude CLI controls](https://code.claude.com/docs/en/cli-usage),
[managed hooks](https://code.claude.com/docs/en/hooks),
[Codex CLI](https://developers.openai.com/codex/cli/reference),
[Codex configuration schema](https://github.com/openai/codex/blob/main/codex-rs/core/config.schema.json).
