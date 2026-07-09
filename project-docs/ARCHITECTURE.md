# Codex/Flywheel Harness Architecture

This document is AUTHORITATIVE. No exceptions.

Status: target architecture and current migration boundary, not a claim that every component is already implemented.

Date: 2026-07-09

## Decision

The harness becomes one enterprise application surface backed by modular flagship services, pubscan repositories, native tooling, and compatibility adapters.

The flagships should not be collapsed into one monolithic codebase. They should be operated as one product through a shared control plane, shared API contracts, shared receipts, shared identity/configuration, shared observability, and shared UI.

The mission is zero mandatory external dependencies. The core harness must run from local files, local executables, local receipts, native rendering/tool surfaces, and local model endpoints. Optional enterprise adapters may add PostgreSQL, object storage, event streams, search, observability, cloud APIs, and richer app shells, but those adapters cannot become prerequisites for the core.

The current constraint is not UI/rendering capability. The system has native tooling and a rendering-engine direction to use. The hard infrastructure gaps are compute, durable storage, scheduling/orchestration around those resources, and receipts/profiles that make those resources accountable.

If you are about to merge `index`, `forum`, `gather`, `crucible`, `telos`, `mneme`, `relay`, `plexus`, and `local-model` into one large package, STOP. Integrate them through typed service boundaries and receipts instead.

If you are about to build another benchmark script that does not emit a receipt, STOP. Add the receipt contract first.

If you are about to add a UI screen that cannot point to a run, model, tool, receipt, artifact, or schematic, STOP. It is likely decoration rather than control-plane functionality.

If you are about to make PostgreSQL, Redis, a vector database, cloud object storage, a browser UI, a desktop shell, or a frontier API mandatory for the core harness, STOP. Those are adapters, not the base requirement.

## Product thesis

One local-first enterprise AI control plane for models, agents, tools, benchmarks, receipts, and self-improvement loops.

It is not primarily a chatbot. It is not only an eval runner. It is a measurable capability engine that can run local and frontier models through the same accountable workflow.

## High-level shape

```text
Operator / Team
     |
     v
Enterprise Harness UI
     |
     v
Control Plane API
     |
     +--> Agent Runtime
     +--> Benchmark Runtime
     +--> Model Foundry
     +--> Tool Registry
     +--> Receipt Ledger
     +--> Docs and Schematic Engine
     |
     v
Flagship Service Boundary
     |
     +--> index    workspace graph and context map
     +--> forum    routing and communication contracts
     +--> gather   source intake and corpus capture
     +--> crucible adversarial eval and pressure testing
     +--> telos    context envelope and control-plane convention
     +--> mneme    memory, provenance, and recall
     +--> relay    event bus and message transport
     +--> plexus   graph planning and dependency orchestration
     +--> local-model endpoints, M7, model cards, release gates
     +--> pubscan public tools and repositories
     +--> native rendering engine and native workstation tools
     |
     v
Data Plane
     |
     +--> File/JSONL/SQLite zero-dependency core
     +--> Optional PostgreSQL source-of-truth adapter
     +--> Optional object store for artifacts and receipts
     +--> Optional vector/search index for acceleration only
     +--> Optional queue/event stream
     +--> Optional observability store
```

## Application areas

| Area | Does | Does NOT |
|---|---|---|
| Mission Control | Shows active runs, agents, tools, queues, endpoint health, failures, receipts, and next actions. | Does not hide failures behind summary cards. |
| Benchmark Lab | Runs M7, adversarial lanes, source-mined lanes, stateful action lanes, and cross-harness comparisons. | Does not reward prose-only answers when executable action is required. |
| Model Foundry | Manages local model profiles, endpoint profiles, 14B/32B release gates, checksums, model cards, quantization notes, and eval promotion. | Does not publish a model without release criteria and benchmark receipts. |
| Tool Registry | Tracks flagship tools, adapters, CLI/MCP surfaces, health, version, owner, retirement criteria, and evidence. | Does not treat installed tools as integrated until health and invocation are proven. |
| Receipt Ledger | Stores byte-witness packets, benchmark artifacts, auth-status receipts, schematic receipts, and run evidence. | Does not store secrets or raw credentials. |
| Agent Runtime | Executes routed agent workflows with explicit tool calls, model choices, receipt emission, and failure taxonomy. | Does not let opaque chat transcripts serve as the only execution record. |
| Docs and Schematics | Generates architecture notes, graph artifacts, model cards, benchmark reports, and drift checks from actual work. | Does not rely on manually maintained diagrams that can drift silently. |

## UI direction

The UI should feel like an instrument panel for an accountable AI engine, not a generic SaaS dashboard.

Design tokens:

| Token | Value | Use |
|---|---|---|
| `ink` | `#15130f` | Primary text and chart labels. |
| `paper` | `#f4efe3` | Default surface. |
| `oxide` | `#9f4b2f` | Warnings, degraded receipts, and adversarial pressure. |
| `verdigris` | `#216c68` | Verified receipts and healthy endpoints. |
| `signal` | `#e0a928` | Active run accents and cursor state. |
| `graphite` | `#2f3437` | Dense runtime panels. |

Typography:

| Role | Typeface direction | Why |
|---|---|---|
| Display | Condensed technical serif or engraved industrial display face. | Gives the product a control-room identity instead of default app typography. |
| Body | Humanist sans with strong numerals. | Readable for reports, run logs, and operational copy. |
| Data | Monospace with clear zero/one separation. | Required for hashes, ports, metrics, model ids, and receipts. |

Signature UI element:

`Receipt Loom`: a vertical run timeline where every model call, tool action, benchmark gate, artifact, and failure folds into an immutable receipt thread. The screen is remembered by the receipt thread, not by decorative gradients.

Primary screens:

| Screen | Primary job | Key widgets |
|---|---|---|
| Dashboard | Answer "what is alive, blocked, proving, or degrading?" | Endpoint health, active runs, receipt freshness, failure queue. |
| Runs | Inspect every agent/model/tool execution. | Run DAG, logs, model calls, tool events, artifacts, replay button. |
| Benchmarks | Compare harnesses and models on the same task sets. | M7 matrix, adversarial matrix, stateful action matrix, deltas, raw artifact links. |
| Models | Manage local and frontier model profiles. | Endpoint cards, quantization, memory footprint, release gate, model card status. |
| Agents | Track routed workflows and permissions. | Maturity tier, tool access, recent failures, promotion gates. |
| Tools | Operate flagships as services. | Health, version, CLI/MCP endpoint, owner, receipts, restart instructions. |
| Receipts | Audit the accountability substrate. | Hash search, byte-witness viewer, diff/drift verdicts, export. |
| Schematics | Maintain architecture as data. | Graph viewer, dependency map, drift warnings, Mermaid export. |
| Settings/Auth | Configure accounts and endpoints without exposing secrets. | Claude/Codex subscription/API lane receipts, OpenCode sidecar config, local endpoints. |

Frontend stack:

| Layer | Choice | Why |
|---|---|---|
| Core UI | Native rendering/tooling plus CLI/TUI/static reports | Preserves zero mandatory dependency posture and uses existing local capability. |
| Rich UI adapter | React + TypeScript | Fast team velocity, mature graph/table ecosystem, easy desktop/web split when dependencies are allowed. |
| Build tool adapter | Vite | Small local-first rich app surface and fast dev loop; optional, not core. |
| Desktop shell adapter | Tauri first, Electron only if required by native automation | Smaller footprint for local model users; optional wrapper, not core. |
| Styling | CSS variables plus scoped component styles | Keeps visual identity explicit and portable. |
| Realtime | WebSocket plus Server-Sent Events fallback | Run logs and health updates need low-friction streaming. |
| Graphs | Cytoscape, React Flow, or Sigma behind an adapter | Schematics and run DAGs must not lock the product to one graph library. |

## Backend shape

The zero-dependency backend core is local scripts, file-backed receipts, and direct executable adapters. The first serious rich backend should be Python/FastAPI because the current harness, benchmark runners, local model utilities, and artifacts are Python-heavy.

Backend components:

| Component | Does | Does NOT |
|---|---|---|
| Control Plane API | Provides typed endpoints for runs, models, tools, receipts, artifacts, config, auth status, and schematics. | Does not execute long jobs inline inside request handlers. |
| Worker Runtime | Runs benchmarks, local model calls, source intake, model release checks, and repair/constrained-output jobs. | Does not mutate production state without emitting receipts. |
| Endpoint Adapter Layer | Normalizes local serve, Ollama, Codex CLI/API, Claude CLI/API, OpenCode sidecar/API, and OpenAI-compatible providers. | Does not proxy subscription tokens or scrape credential stores. |
| Receipt Service | Writes content-addressed evidence, validates byte witnesses, and indexes receipt summaries. | Does not store raw secrets or unverifiable success claims. |
| Schematic Service | Maintains `architecture.graph.json`, Mermaid exports, and drift gates. | Does not allow docs to drift silently from service reality. |
| Tool Service Gateway | Wraps flagships through CLI/MCP/API adapters. | Does not require every flagship to share one runtime or language. |

## Service responsibility map

| Service | Owns | Inputs | Outputs | Current integration posture |
|---|---|---|---|---|
| `index` | Workspace graph, docs map, router context. | Workspace paths, docs, source files. | Graph JSON, router maps. | Integrated but current MCP transport has shown `Transport closed` and needs reload/resilience. |
| `forum` | Routing and communication contract. | Task text, domain signals. | Route frame, proof lane, delivery profile. | Callable and used for architecture/model-foundry routing. |
| `gather` | Source intake. | URLs, public sources, consented APIs. | Corpus artifacts, source receipts. | Added Discord intake behind official bot API boundary. |
| `crucible` | Adversarial pressure. | Benchmark cases, artifacts, witness packets. | Failure taxonomy, pressure scores. | Represented through adversarial benchmark lanes. |
| `telos` | Context envelope and conventions. | Tool manifests, room/context requests. | Context envelope, server manifest. | Available as coordination/control-plane convention. |
| `mneme` | Memory and provenance. | Runs, artifacts, retrieved context. | Recall packets, memory receipts. | Audited for readiness; hardening remains. |
| `relay` | Event transport. | Run events, tool events, health changes. | Event stream, durable messages. | Audited for readiness; should become event backbone. |
| `plexus` | Graph planning and schematic orchestration. | Tasks, dependency graphs, service maps. | Plans, DAGs, schematic deltas. | Priority hardening target because it connects UI schematics to routing. |
| `local-model` | Model endpoints, benchmark harness, M7, release track. | Models, prompts, fixtures, source datasets. | Benchmark reports, model cards, release evidence. | Active implementation area with multiple benchmark artifacts. |
| `pubscan` | Public repo/tool universe under `C:\dev\public\pubscan`. | Local source repos, built executables, language assets, public site assets. | Tool profiles, build receipts, source-mined benchmarks, release docs. | Required integration surface; top-level inventory exists, per-repo adapters pending. |
| native rendering/tools | Existing local rendering and native workstation capability. | Render jobs, UI states, visual artifacts, schematics, previews. | Rendered UI, diagrams, screenshots, visual receipts, native reports. | Existing capability to integrate; exact path/profile still needs a tool-profile receipt. |

## Pubscan repository surface

All top-level repositories under `C:\dev\public\pubscan` are in-scope tool/repo surfaces.

Current bounded inventory:

| Repo/tool | Path | Initial harness posture |
|---|---|---|
| `calibrate-pro` | `C:\dev\public\pubscan\calibrate-pro` | Pubscan tool profile required. |
| `emet` | `C:\dev\public\pubscan\emet` | Pubscan tool profile required. |
| `HarperZ9` | `C:\dev\public\pubscan\HarperZ9` | Pubscan tool profile required. |
| `HarperZ9.github.io` | `C:\dev\public\pubscan\HarperZ9.github.io` | Pubscan tool profile required. |
| `linguist` | `C:\dev\public\pubscan\linguist` | Pubscan tool profile required. |
| `linguist-add-quantalang` | `C:\dev\public\pubscan\linguist-add-quantalang` | Pubscan tool profile required. |
| `quanta-color` | `C:\dev\public\pubscan\quanta-color` | Pubscan tool profile required. |
| `quantalang` | `C:\dev\public\pubscan\quantalang` | Already connected to buildc receipt/benchmark work; still needs formal pubscan profile. |
| `quantalang-tmLanguage` | `C:\dev\public\pubscan\quantalang-tmLanguage` | Pubscan tool profile required. |
| `quantalang-vscode` | `C:\dev\public\pubscan\quantalang-vscode` | Pubscan tool profile required. |
| `quanta-universe` | `C:\dev\public\pubscan\quanta-universe` | Pubscan tool profile required. |
| `quanta-universe-fix-codegen-prefixing` | `C:\dev\public\pubscan\quanta-universe-fix-codegen-prefixing` | Pubscan tool profile required. |
| `wol-pi` | `C:\dev\public\pubscan\wol-pi` | Pubscan tool profile required. |

Each pubscan repo must be represented as `harness.tool-profile/v1` before the enterprise UI can claim full tool coverage.

## Middleware, chain, and native tooling compatibility

The harness must support all middleware, infrastructure chains, and existing tools through adapters:

| Chain | Core behavior | Optional adapter behavior |
|---|---|---|
| Rendering/UI | Native rendering/tooling plus static reports. | Browser/desktop app shell, graph canvas, live preview service. |
| Storage | Local filesystem content-addressed artifact store. | S3-compatible object store. |
| State | JSONL/SQLite local state. | PostgreSQL. |
| Events | In-process queue or append-only event log. | Relay, Redis Streams, NATS. |
| Search | Local lexical search and index artifacts. | LanceDB, Qdrant, or other vector/search systems. |
| Auth | Local operator mode and non-secret auth receipts. | OIDC/SAML/RBAC. |
| Observability | Local JSONL logs and receipts. | OpenTelemetry, Prometheus, Grafana, log store. |
| Models | Dry fixtures, local serve, Ollama, local OpenAI-compatible endpoints. | Codex API, Claude API, frontier APIs, OpenCode sidecar. |
| Tools | CLI/file/MCP adapters. | HTTP/gRPC/remote service adapters. |
| Compute | Local CPU/GPU profiles and dry fixtures. | Remote GPU, lab cluster, cloud batch, or rented compute adapter. |

## Runtime data flow

```text
User starts run in UI
     |
     v
Control Plane API creates run record in PostgreSQL
     |
     v
Relay publishes run.created event
     |
     v
Worker claims run
     |
     +--> Forum selects route contract
     +--> Index supplies workspace graph/context
     +--> Mneme supplies memory/provenance context
     +--> Model Foundry selects endpoint/model profile
     +--> Tool Gateway invokes required flagship tools
     |
     v
Worker emits events, artifacts, and receipts
     |
     +--> PostgreSQL stores normalized run/tool/model state
     +--> Object store stores raw artifacts and byte-witness packets
     +--> Vector/search index stores accelerators only
     |
     v
UI streams progress and renders Receipt Loom
     |
     v
Benchmark/doc/schematic gates decide promotion, fold, retry, or release block
```

## Data contract priorities

The shared contracts matter more than a large UI shell.

Required v1 schemas:

| Schema | Purpose |
|---|---|
| `harness.run/v1` | Durable run state and lifecycle. |
| `harness.event/v1` | Append-only event stream row. |
| `harness.receipt/v1` | Receipt metadata and content-addressed artifact pointer. |
| `harness.model-profile/v1` | Local/frontier model identity, endpoint, quantization, limits, and release state. |
| `harness.tool-profile/v1` | Tool identity, invocation surface, health, owner, version, dependency posture, and retirement criteria. |
| `harness.benchmark-result/v1` | Comparable metrics, raw artifact paths, failure classes, and deltas. |
| `harness.endpoint-auth-status/v1` | Non-secret Claude/Codex/OpenCode/local endpoint auth posture. |
| `harness.architecture-graph/v1` | Nodes, edges, responsibilities, ports, and drift metadata. |

## Promotion ladder

| Stage | Condition | Evidence |
|---|---|---|
| Repo/profile | A local repo or tool is inventoried without installing dependencies. | `harness.tool-profile/v1` row and path evidence. |
| Script | A local command exists and emits a useful artifact. | CLI output and artifact path. |
| Receipt-producing tool | Command emits schema, hash, metrics, and failure class. | JSON receipt and catalog entry. |
| Control-plane adapter | API can start, observe, and stop the workflow. | API route, run record, event stream. |
| UI-operated capability | Operator can run and inspect it from the UI. | UI screen, live events, artifact links. |
| Enterprise capability | Auth, RBAC, audit, retention, health, CI gate, docs, ownership, and support policy exist. | Enterprise readiness checklist and release receipt. |

## Current known non-completions

The following are architectural gaps, not failures of the design:

- No unified app shell exists yet.
- No FastAPI control-plane service exists yet.
- PostgreSQL schema is not implemented yet.
- Relay is not yet the event backbone for all tools.
- Plexus does not yet own schematic graph maintenance.
- Pubscan repositories have a bounded top-level inventory, but most do not yet have formal tool profiles, health checks, or adapters.
- Native rendering/tooling is treated as existing capability, but it still needs a concrete profile and receipt path in the Tool Registry.
- Compute and durable storage are the real capacity gaps and need explicit resource profiles.
- OpenCode is wired as an endpoint adapter, but live benchmark rows still require a reachable sidecar/server and credentials.
- Claude/Codex subscription/API lanes have a status receipt command, but the current account state still needs a fresh local receipt run.
- Index MCP is conceptually required, but the current in-process MCP transport has recently returned `Transport closed`.

## Next executable architecture slice

Build the thinnest useful zero-dependency control plane:

1. `packages/harness_core`: shared schemas and receipt helpers with file-backed operation.
2. Pubscan tool-profile generator for `C:\dev\public\pubscan`.
3. Native rendering/tool profile and receipt adapter.
4. Local run/event/receipt store backed by JSONL or SQLite.
5. Compute profile schema for local CPU/GPU, remote GPU, lab cluster, and dry-fixture capacity.
6. Storage profile schema for local filesystem, content-addressed artifact store, and optional object storage.
7. First adapters: existing benchmark scripts, endpoint auth status, OpenCode status, M7 run ingestion, pubscan repo profiles.
8. Optional `apps/control-plane-api`: FastAPI service with `/health`, `/runs`, `/tools`, `/models`, `/receipts`, `/schematics`.
9. Optional `apps/harness-ui`: rich app shell with Dashboard, Runs, Benchmarks, Models, Tools, Receipts, Schematics, Settings.
