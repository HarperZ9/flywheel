# Pubscan and Zero-Dependency Integration Contract

Date: 2026-07-09

Status: integration contract and inventory, not proof that every pubscan repository is already adapted into the runtime.

## Decision

All public `pubscan` tools and repositories are part of the harness tool universe.

The harness mission is zero mandatory external dependencies. The core must orient, run local workflows, emit receipts, render local/native views, and degrade gracefully with only local files, local executables, native tooling, and standard runtime surfaces. Rich infrastructure is allowed as an adapter, never as a hard prerequisite.

Rendering/UI is not the missing primitive. Native rendering and native workstation tooling are treated as existing capability surfaces to integrate. The scarce layers are compute, durable storage, scheduling/orchestration around those resources, and receipts/profiles that make resource use accountable.

## Verified pubscan inventory

Bounded top-level inventory of `C:\dev\public\pubscan` found:

| Name | Path |
|---|---|
| `calibrate-pro` | `C:\dev\public\pubscan\calibrate-pro` |
| `emet` | `C:\dev\public\pubscan\emet` |
| `HarperZ9` | `C:\dev\public\pubscan\HarperZ9` |
| `HarperZ9.github.io` | `C:\dev\public\pubscan\HarperZ9.github.io` |
| `linguist` | `C:\dev\public\pubscan\linguist` |
| `linguist-add-quantalang` | `C:\dev\public\pubscan\linguist-add-quantalang` |
| `quanta-color` | `C:\dev\public\pubscan\quanta-color` |
| `quantalang` | `C:\dev\public\pubscan\quantalang` |
| `quantalang-tmLanguage` | `C:\dev\public\pubscan\quantalang-tmLanguage` |
| `quantalang-vscode` | `C:\dev\public\pubscan\quantalang-vscode` |
| `quanta-universe` | `C:\dev\public\pubscan\quanta-universe` |
| `quanta-universe-fix-codegen-prefixing` | `C:\dev\public\pubscan\quanta-universe-fix-codegen-prefixing` |
| `wol-pi` | `C:\dev\public\pubscan\wol-pi` |

## Zero-dependency rule

The harness has two layers:

| Layer | Dependency posture | Purpose |
|---|---|---|
| Core | Zero mandatory external services and minimal runtime dependencies. | Local operation, receipts, benchmark orchestration, artifact indexing, adapter discovery, failure taxonomy. |
| Adapters | Optional dependencies. | PostgreSQL, Redis, Relay, NATS, Qdrant, LanceDB, OpenTelemetry, browser UI, desktop shell, cloud object storage, enterprise auth. |

If an adapter is missing, the harness must fold to a local equivalent:

| Missing adapter | Fold-to behavior |
|---|---|
| PostgreSQL | SQLite or JSONL/file-backed store. |
| Redis/NATS/Relay | In-process queue or append-only event log. |
| S3/object storage | Local filesystem content-addressed artifact store. |
| Vector DB | Local lexical search, index graph, or no retrieval acceleration. |
| OpenTelemetry | Local JSONL logs and receipt events. |
| Browser UI | CLI/TUI and static HTML report output. |
| Rich rendering service | Native rendering/tooling and static visual artifacts. |
| Frontier API | Local model endpoint, dry fixture, or explicit unavailable receipt. |
| Pubscan tool dependency | Adapter marks unavailable or runs local executable if present. |
| Remote compute | Local CPU/GPU profile, smaller model, queued run, or dry fixture. |
| Object storage capacity | Local content-addressed filesystem store and retention policy. |

## Compatibility doctrine

The harness must be compatible with all middleware, infrastructure chains, and existing tools by using a stable adapter contract.

Required adapter surfaces:

| Surface | Contract |
|---|---|
| CLI | `discover`, `health`, `run`, `emit_receipt`, `explain_failure`. |
| HTTP/API | `GET /health`, `POST /run`, `GET /runs/{id}`, `GET /receipts/{id}` where implemented. |
| MCP | Tool manifest, schema, invocation envelope, receipt pointer. |
| File artifact | Input path, output path, schema id, SHA-256, provenance. |
| Event stream | `run.created`, `tool.started`, `tool.finished`, `receipt.written`, `run.failed`. |
| DB adapter | `insert_run`, `append_event`, `put_receipt`, `get_artifact`, `query_scorecards`. |
| Model endpoint | OpenAI-compatible `/v1`, Ollama, local serve, CLI subscription, API key, or dry fixture. |
| Rendering/native tool | Input artifact, render command, output artifact, visual receipt, failure class. |
| Compute profile | Device/runtime identity, capacity, queue posture, cost, and benchmark eligibility. |
| Storage profile | Root path or object store, free capacity, retention class, hash policy, and artifact limits. |

Required compatibility lanes:

| Lane | Requirement |
|---|---|
| Local filesystem | Always available baseline. |
| Local executables | First-class, including pubscan-built tools such as `buildc.exe` when present. |
| Git repositories | Treated as corpus and tool surfaces, not only source code. |
| Python tools | Callable through scripts or module entrypoints. |
| Node/desktop tools | Callable only through explicit CLI/API/sidecar contracts. |
| Rust/C/C++ tools | Callable through local executable adapters. |
| Native rendering engine | Treated as a core local tool surface once profiled. |
| Middleware | Optional adapters for DB, queue, object store, search, auth, observability. |
| Harnesses | Codex, Flywheel, Claude Code, OpenCode, local model endpoints. |
| Compute/storage chain | Explicit profiles for local CPU/GPU, remote GPU, storage root, artifact capacity, and retention. |

## Integration requirement for each pubscan repo

Every pubscan repo should get a `tool-profile` row before it is considered integrated:

```json
{
  "schema": "harness.tool-profile/v1",
  "id": "pubscan.<name>",
  "path": "C:\\dev\\public\\pubscan\\<name>",
  "surfaces": ["repo"],
  "health": "unknown",
  "entrypoints": [],
  "receipts": [],
  "owner": "operator",
  "dependency_posture": "zero-mandatory",
  "retirement_criteria": "explicit operator retirement or replaced by a receipt-compatible successor"
}
```

## Next executable step

Implemented command:

```powershell
python scripts/run_pubscan_resource_profiles.py --out C:/tmp/pubscan_resource_profiles_20260709.json --markdown-out C:/tmp/pubscan_resource_profiles_20260709.md
```

The command is designed to:

1. Reads top-level `C:\dev\public\pubscan` directories.
2. Detects obvious entrypoints without installing dependencies.
3. Emits `harness.pubscan-tool-profiles/v1`.
4. Marks each row as `available`, `source-only`, `needs-build`, `missing-entrypoint`, or `unverified`.
5. Writes a receipt into the artifact store.

This converts pubscan from a loose repository folder into a first-class harness tool universe without violating zero mandatory dependency posture.

Second immediate step:

Create compute and storage profile receipts:

```json
{
  "schema": "harness.resource-profile/v1",
  "compute": {
    "local_cpu": "available",
    "local_gpu": "unknown",
    "remote_gpu": "not_configured",
    "queue": "local"
  },
  "storage": {
    "artifact_root": "C:\\tmp",
    "content_addressed": true,
    "retention_policy": "local-dev"
  }
}
```

This makes compute/storage scarcity measurable instead of implicit.

Current limitation:

- The command has been added but not run in this slice because this session's validation rule requires explicit user approval before running checks or probes.
