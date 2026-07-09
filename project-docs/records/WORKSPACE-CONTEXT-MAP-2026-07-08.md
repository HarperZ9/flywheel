# Workspace Context Map - 2026-07-08

## Scope

This record captures the current evidence map for the Codex/Flywheel local-model harness workstream.

Primary corpus:
- `C:\dev`
- `C:\dev\local-model`
- `C:\dev\public\mneme`
- `C:\dev\public\relay`
- `C:\dev\public\plexus`
- `E:\local-model-run`
- `C:\tmp\m7_*.json`

## Tool Routing Evidence

Verified from current Codex configuration:
- `index` is configured as an MCP server with `PYTHONPATH=C:/dev/public/index/src`.
- `forum` is configured as an MCP server with `PYTHONPATH=C:/dev/public/forum/src`.
- `gather`, `crucible`, `telos`, and `aleph` are configured as MCP servers.
- `C:\dev`, `C:\dev\local-model`, and flagship public repos are trusted projects.

Verified by tool use:
- `index.map` scanned `C:/dev` and reported 186 repositories.
- `forum.doctor` returned `MATCH`.
- `forum.route` classified the work as model-foundry validation/architecture, with escalation because it crosses harnesses, tools, benchmarks, models, and product hardening.

Retired surface:
- Safe-everything is retired.
- Active `safe-*` skills were moved to `C:\Users\Zain\.agents\skills.retired\safe-everything-2026-07-08`.
- `C:\Users\Zain\.codex\hooks.json` no longer contains behavior-transform or safe redirect hooks.

## Repository Map

`C:\dev\local-model`
- Role: local model harness, flywheel benchmark scripts, executable packaging, local endpoint server.
- Status: active and dirty from current work.
- Notable live artifacts: `artifacts\exe\local-agent.exe`, `artifacts\exe\local-serve.exe`.

`C:\dev\public\mneme`
- Role: memory/provenance tool.
- Status from audit: shippable small Python library prototype, not enterprise-ready.
- Verified tests from subagent: `82 passed in 3.36s`.

`C:\dev\public\relay`
- Role: local agent/harness bridge and endpoint compatibility layer.
- Status from audit: clean stdlib prototype, not enterprise-ready.
- Verified tests from subagent: `53 passed in 4.37s`.

`C:\dev\public\plexus`
- Role: interop graph/registry layer.
- Status from audit: compact working prototype, not enterprise-ready.
- Verified tests from subagent: `31 passed in 0.07s`.

## Runtime State

Verified by subagent:
- `http://127.0.0.1:8765/health` is live and reports `Qwen2.5-Coder-14B-Instruct (base, nf4)`.
- `serve.py` exposes `/generate`, `/chat/completions`, and, after current patch, `/v1/messages`.
- Ollama is live on `11434` with `qwen2.5:7b`, `qwen2.5:3b`, and `qwen2.5:0.5b`.
- Ports `8000`, `8001`, and `8002` were not open in the subagent pass.
- `opencode` command was not present in PATH in the subagent pass.

## Model Artifacts

Base models:
- `E:\local-model-run\models\Qwen2.5-Coder-14B-Instruct`
- `E:\local-model-run\models\Qwen2.5-Coder-32B-Instruct`

Project-owned derivatives:
- 14B adapter candidate: `E:\local-model-run\checkpoints\phase2-linux-qlora-cpt-14b\checkpoint-2020`
- 32B smoke checkpoint: `E:\local-model-run\checkpoints\phase2-linux-qlora-cpt-32b-smoke\checkpoint-2`

Current release posture:
- 14B can enter publish-prep after model-card, manifest, benchmark, safety, and checksum evidence.
- 32B is smoke-only and should remain internal until a full training/evaluation run exists.

## Scratch And Session Context

Local scan found current Codex session artifacts under:
- `C:\Users\Zain\.codex\sessions\2026\07\07\rollout-2026-07-07T18-20-24-019f3f4f-c0e1-7c81-9f98-92d8bd3d9046.jsonl`
- `C:\Users\Zain\.codex\sessions\2026\07\08\rollout-2026-07-08T15-18-12-019f43cf-5093-7650-a232-7161750455fa.jsonl`
- `C:\Users\Zain\.codex\sessions\2026\07\08\rollout-2026-07-08T15-18-19-019f43cf-65c9-70d1-a620-b1246b12963b.jsonl`
- `C:\Users\Zain\.codex\sessions\2026\07\08\rollout-2026-07-08T15-18-19-019f43cf-7e8e-7ab2-8b6c-9d31ddb270d1.jsonl`
- `C:\Users\Zain\.codex\sessions\2026\07\08\rollout-2026-07-08T15-18-30-019f43cf-95bd-72f3-aa3a-e2d954e1a503.jsonl`
- `C:\Users\Zain\.codex\sessions\2026\07\08\rollout-2026-07-08T15-18-36-019f43cf-ab6a-7e51-a83a-4fd670f3cffe.jsonl`
- `C:\Users\Zain\.codex\sessions\2026\07\08\rollout-2026-07-08T15-18-42-019f43cf-c180-7e53-a479-2bee6c9e12bd.jsonl`

Open scratch/session archaeology remains incomplete until the dedicated scratch subagent returns or a deeper filtered pass is run.

## Immediate Next Loop

System activity -> wire client-compatible local endpoint route.
Observed friction -> Messages API facade existed but HTTP server returned 404.
Capability improvement -> `/v1/messages` route with receipt header and typed errors.
Future improvement -> Claude-style clients can target the same local model endpoint used by benchmark harnesses.
Next trigger -> run live `/v1/messages` smoke against `127.0.0.1:8765` after restarting the server with the patched code.
