# Mneme, Relay, Plexus Enterprise Readiness - 2026-07-08

## Summary

All three tools are working prototypes with real tests and useful capabilities. None of the three is enterprise-ready or feature-complete for the requested target state.

## Mneme

Status:
- Shippable as a small `0.1.0` local Python library.
- Not enterprise-ready.

Verified by subagent:
- `python -m pytest -q` -> `82 passed in 3.36s`.
- Wheel build and installed CLI smoke succeeded.
- `mneme bench` reported `token_reduction: 0.7664`, `answer_recall: 1.0`.

Implemented capabilities:
- Layered memory.
- BM25 / hybrid recall.
- Provenance receipts.
- Drift checks.
- Audit tombstones.
- Temporal supersede/history.
- Gather-shaped ingest.
- Crucible-shaped export.
- Entity graph.
- Scenarios.
- Inspector.
- Benchmark command.
- Stdio MCP with six tools.

Major gaps:
- Tenant isolation is app-level, not a hard boundary.
- `turns` table lacks the same user/session scoping posture as `memories`.
- MCP schemas omit user/session scoping for recall.
- Drift does not bind source content hashes strongly enough for enterprise provenance.
- No schema migration strategy or production SQLite posture.
- CI lacks lint, type check, coverage, security scan, SBOM, dependency review, and attestations.
- Docs and release notes disagree on test counts and MCP tool count.
- Missing `SECURITY.md`, `SUPPORT.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `.github\dependabot.yml`, `.github\CODEOWNERS`, `.pre-commit-config.yaml`, docs/API reference, and `py.typed`.

Priority edits:
- `C:\dev\public\mneme\src\mneme\store.py`
- `C:\dev\public\mneme\src\mneme\drift.py`
- `C:\dev\public\mneme\src\mneme\receipt.py`
- `C:\dev\public\mneme\src\mneme\mcp.py`
- `C:\dev\public\mneme\.github\workflows\ci.yml`
- `C:\dev\public\mneme\.github\workflows\release.yml`
- `C:\dev\public\mneme\README.md`
- `C:\dev\public\mneme\CHANGELOG.md`
- `C:\dev\public\mneme\DELIVERY.md`

## Relay

Status:
- Clean stdlib prototype with good hermetic tests.
- Not enterprise-ready.

Verified by subagent:
- `python -m pytest -q -p no:cacheprovider` -> `53 passed in 4.37s`.
- `python -m relay --help` works.
- Source repo stayed clean in the audit pass.

Major gaps:
- README advertises a served `14B/32B (serve.py)` path, but relay itself has no tracked `serve.py` or server module.
- MCP bridge is not at CLI parity.
- Claude Code, OpenCode, and Codex compatibility is claimed but not packaged with docs/config/smokes.
- `run` tool uses `shell=True` and denylist logic that is explicitly not a security boundary.
- Online mode can send local file/tool output to hosted providers without enough data-boundary controls.
- Benchmark/eval hooks are absent beyond test repair.
- Endpoint health mostly proves credential/env presence, not live service readiness.
- Packaging CI only wheel-smokes `relay --help`.

Priority edits:
- Add or remove/clarify relay-owned `serve.py` claim.
- Extend MCP inputs/outputs for CLI parity.
- Add `docs\claude-code.md`, `docs\opencode.md`, `docs\codex.md`, and sample MCP config files.
- Replace shell command execution with allowlisted argv execution, controlled env, resource limits, audit log, and optional OS/container sandbox mode.
- Add benchmark scripts for latency, endpoint failover, MCP round-trip, edit-task pass rate, and tool-loop reliability.

## Plexus

Status:
- Compact working `0.2.0` prototype.
- Not enterprise-ready.

Verified by subagent:
- `31 passed in 0.07s`.
- CLI surfaces work.
- Built-in and JSON manifest discovery round-trip.

Major gaps:
- Grounding is asserted but not independently verified.
- External manifest labels can break Mermaid/DOT rendering.
- Raw CLI text can emit unsafe shell scripts.
- Manifest validation is too weak for enterprise interop.
- Runnable pipeline is mostly a sketch, not artifact handoff execution.
- MCP surface is minimal and not a full enterprise registry.
- Benchmark/report integration is absent.
- Missing enterprise hygiene files and stronger CI gates.

Priority edits:
- Add `C:\dev\public\plexus\src\plexus\grounding.py`.
- Escape Mermaid/DOT labels and generate collision-safe node IDs.
- Replace shell script emission with structured execution plan JSON by default.
- Add JSON Schema validation and reject unknown fields by default.
- Add benchmark/report modules and CI artifacts.
- Add `SECURITY.md`, `CONTRIBUTING.md`, `.github\CODEOWNERS`, `.github\dependabot.yml`, release workflow, pre-commit, lint/type/coverage checks.

## Enterprise Definition Of Done

Each tool needs:
- stable CLI/MCP interface
- install/config docs
- client integration examples
- security and secret-handling posture
- test, lint, type, coverage, and package gates
- release workflow
- known limitations
- migration/compatibility story
- owner and maintenance policy
- benchmark/report integration

## Next Recursive Loop

System activity -> harden one tool at a time.
Observed friction -> all three have useful cores but weak enterprise surfaces.
Capability improvement -> shared enterprise release checklist and CI template.
Future improvement -> mneme, relay, and plexus can share quality gates instead of hand-rolled release posture.
Next trigger -> choose the first target repo and implement a bounded enterprise slice.
