# MCP parity design note, 2026-09-08

Problem: Flywheel can safely bind a Relay-backed run only if Relay's MCP background run surface admits the same execution dials its CLI already supports and reports the immutable request alongside the result. Today `relay --agent` supports backend/model/max-token/check/test-cmd/compact-budget controls, while `local_agent_start` and `local_agent_run` only declare goal/root/write/exec/max-steps/online.

Scope for this change:

- Extend `local_agent_run` and `local_agent_start` request schemas to cover the existing CLI-backed options that already have Relay implementation support: `backend`, `model`, `max_tokens`, `check`, `test_cmd`, and `compact_budget`.
- Pass those fields into the existing `LocalAgent`, `ToolExecutor`, and `run_agent` paths. Do not add a provider loop or a new executor.
- Include a request-binding projection in both blocking and background results so a caller can compare requested backend/model/root/effective gates/checks against the last witnessed assistant route.
- Keep the background API compatible: `local_agent_start` still returns `{run_id, state}` immediately, and existing status/result polling remains valid.

Controls required by tests:

- Write denial keeps the file unchanged.
- Exec denial prevents `test_cmd` from running and leaves the run unaccepted.
- Unsupported backend returns a typed failure with request binding, not a false success.
- Failed checks leave `accepted=false`.
- Background request binding survives poll/result and, where the existing persisted-run architecture supports it, reload from disk.
