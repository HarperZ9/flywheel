# Codex/Flywheel Harness Infrastructure

This document is AUTHORITATIVE. No exceptions.

Status: target infrastructure and migration plan, not a claim that every component is already deployed.

Date: 2026-07-09

## Infrastructure decision

Use a zero-mandatory-dependency local-first stack that can graduate to team/server deployment without rewriting the harness.

Default development mode must run on one workstation with local files, local executables, native rendering/tooling, and local model endpoints. Enterprise mode must support multi-user auth, durable queues, centralized object storage, audit retention, service health management, and larger compute/storage adapters without making them mandatory.

If you are about to require Kubernetes for local development, STOP. The first-class path is workstation-local.

If you are about to use a vector database as the system of record, STOP. SQL and receipts are the source of truth.

If you are about to put secrets in benchmark artifacts, STOP. Receipts may record secret presence and hash-safe metadata only.

If you are about to make any middleware required for basic harness operation, STOP. Middleware must be adapterized.

If you are about to treat rendering/UI as the missing primitive, STOP. Native rendering/tooling exists as a local capability surface; compute and storage are the scarce resource layers that need profiles and adapters.

## Deployment modes

| Mode | Purpose | Required services |
|---|---|---|
| `local-core` | Single operator, zero mandatory external services. | Local scripts, local files, JSONL/SQLite, filesystem receipts, native rendering/tooling, local executables, local model endpoints. |
| `local-dev` | Single operator building and benchmarking on one workstation. | API, UI, SQLite or local PostgreSQL, filesystem object store, local workers. |
| `local-enterprise` | Workstation or lab server with durable state and multiple local endpoints. | API, UI, PostgreSQL, Redis or Relay, filesystem/S3-compatible object store, workers, OpenTelemetry collector. |
| `team-server` | Shared enterprise deployment. | API, UI, PostgreSQL HA option, Redis/NATS/Relay, S3-compatible object store, auth provider, workers, observability stack. |
| `airgap` | Offline local model evaluation and release gating. | API, UI, local DB, local object store, local model endpoints, local docs and model-card artifacts. |

## Recommended stack

| Layer | Local-first choice | Enterprise choice | Why |
|---|---|---|---|
| Core orchestration | Python stdlib scripts and local executables | Same plus service wrappers | Preserves zero mandatory dependency posture. |
| Core rendering/UI | Native rendering/tooling plus CLI/TUI/static reports | Same as fallback | Uses existing local capability and does not require a browser stack. |
| API adapter | FastAPI | FastAPI behind reverse proxy | Aligns with current Python benchmark harness when service mode is enabled. |
| Rich UI adapter | Vite + React + TypeScript | Same static app behind authenticated proxy | Portable web/desktop target when optional dependencies are allowed. |
| Desktop shell | Tauri optional | Tauri or browser | Smaller footprint than Electron unless deep desktop automation is required. |
| DB | SQLite for throwaway dev, PostgreSQL for real runs | PostgreSQL | SQL is the source of truth. |
| Vector/search | LanceDB local | Qdrant or LanceDB service | Acceleration only, not authority. |
| Queue/events | In-process dev queue, Redis, or Relay | Relay/NATS/Redis Streams | Workers need durable event flow. |
| Object store | Filesystem adapter | S3-compatible bucket | Receipts and artifacts should be content-addressable. |
| Observability | Local JSONL plus OpenTelemetry optional | OpenTelemetry collector, Prometheus, Grafana, log store | Enterprise debugging requires traces and metrics. |
| Secrets | Environment and OS vault | Vault/KMS/secret manager | Secrets must not enter receipts. |
| Auth | Local operator mode | OIDC/SAML plus RBAC | Team mode needs identity and audit. |

## Port assignments

| Service | Default port | Notes |
|---|---:|---|
| Harness Control Plane API | `8780` | Proposed FastAPI service. |
| Harness UI | `8781` | Vite dev server or static preview. |
| Relay event bus | `8782` | If Relay exposes HTTP/WebSocket locally. |
| Model serve endpoint | `8765` | Existing flywheel local serve default. |
| Ollama | `11434` | Existing Ollama default. |
| OpenCode sidecar | operator assigned | Packaged desktop sidecar uses random password and configurable port. |
| PostgreSQL | `5432` | Standard local/team DB. |
| Redis | `6379` | Optional queue/cache. |
| Qdrant | `6333` | Optional vector service. |
| OpenTelemetry collector | `4317` / `4318` | Optional traces/metrics. |

## Core database model

PostgreSQL tables:

| Table | Purpose |
|---|---|
| `workspaces` | Root paths, project identity, policy, and active profile. |
| `runs` | Run lifecycle, provider, model, task type, status, timing, and summary metrics. |
| `run_events` | Append-only event log for tool/model/worker/UI events. |
| `models` | Model profiles, endpoint type, quantization, local path, provider id, and release state. |
| `tools` | Flagship and adapter registry, health, owner, version, endpoint, and retirement criteria. |
| `benchmarks` | Benchmark suites, cases, weights, versions, and source datasets. |
| `benchmark_results` | Row-level scorecards, failure classes, deltas, and artifact references. |
| `receipts` | Content-addressed receipt metadata, hash, schema, verdict, and storage pointer. |
| `artifacts` | Object-store pointers for reports, JSON outputs, logs, model cards, and screenshots. |
| `schematics` | Architecture graph versions, Mermaid exports, drift status, and source receipts. |
| `auth_status` | Non-secret endpoint account posture for Claude, Codex, OpenCode, local providers. |
| `agent_profiles` | Agent identity, maturity tier, permitted tools, promotion gates, and recent failures. |
| `datasets` | Dataset identity, provenance, license, checksum, and benchmark coverage. |
| `pubscan_tools` | Top-level public repo/tool profiles under `C:\dev\public\pubscan`, entrypoints, health, dependency posture, and receipts. |
| `compute_profiles` | Local CPU/GPU, remote GPU, lab cluster, rented compute, and dry-fixture capacity profiles. |
| `storage_profiles` | Local filesystem, content-addressed store, and optional object-store profiles. |

Vector/search stores:

| Store | Purpose | Authority boundary |
|---|---|---|
| `memory_chunks` | Semantic retrieval over docs, runs, artifacts, and source material. | Acceleration only. SQL/artifacts remain authority. |
| `code_index` | Fast lookup over code symbols and docs. | Acceleration only. `index` and source files remain authority. |
| `receipt_search` | Searchable receipt summaries. | Acceleration only. Receipt files and hashes remain authority. |

## Secret handling

Allowed:

- API keys in environment variables or local vault.
- Subscription auth inside official CLI stores.
- Secret presence booleans in receipts.
- Secret-safe provider names, account lane names, and command paths.

Not allowed:

- Printing token values.
- Storing `.env` in git.
- Copying CLI token stores into harness artifacts.
- Sending subscription credentials through another provider or proxy.
- Writing secret-bearing logs to object store.

## Worker classes

| Worker | Responsibilities |
|---|---|
| `benchmark-worker` | Runs M7, source-mined, adversarial, stateful, and provider matrices. |
| `model-worker` | Starts/probes local endpoints, records model profile evidence, handles release checks. |
| `tool-worker` | Calls index/forum/gather/crucible/telos/aleph/mneme/relay/plexus/pubscan adapters and records health. |
| `pubscan-worker` | Inventories pubscan repos, detects entrypoints, runs local health checks, and emits tool-profile receipts without installing dependencies. |
| `resource-worker` | Tracks compute and storage profile availability, cost, capacity, and failure posture. |
| `receipt-worker` | Hashes artifacts, verifies byte witnesses, updates receipt ledger. |
| `docs-worker` | Updates reports, model cards, architecture notes, and schematic exports from receipts. |
| `repair-worker` | Runs constrained-output repair or schema validation without awarding unsupported success. |

## Enterprise readiness gates

| Gate | Required evidence |
|---|---|
| Install | Scripted local install path and pinned dependencies. |
| Start | One command starts API, UI, workers, and local storage in dev mode. |
| Health | `/health` plus per-tool and per-endpoint health receipts. |
| Auth | Claude/Codex/OpenCode/local endpoint status receipts without secret exposure. |
| Run | UI can launch a benchmark and stream progress. |
| Artifact | Every run writes JSON and human-readable artifacts. |
| Receipt | Every artifact has hash, schema, and storage pointer. |
| DB | Run state persists across process restart. |
| Queue | Long jobs do not run inside HTTP request handlers. |
| Docs | Architecture and infrastructure docs update with linked evidence. |
| Drift | Schematic graph changes are detectable. |
| Release | 14B/32B model cards, checksums, endpoint profiles, and benchmark gates exist before publication. |
| Zero dependency | Core functions run with local files/executables/native rendering and fold when optional adapters are absent. |
| Pubscan coverage | Every top-level `C:\dev\public\pubscan` repo has a tool profile and integration status. |
| Compute/storage | Every benchmark or model release declares the compute and storage profile it used. |

## Failure posture

The enterprise competitor claim only works if failures are first-class.

| Failure | Correct behavior |
|---|---|
| Model emits prose instead of action JSON | Fail closed with `malformed_action_json`, optionally attempt receipt-preserving repair. |
| Repair emits empty actions | Fail closed. Empty action arrays are not success. |
| Provider account unavailable | Record provider error and auth-status receipt. Do not call it model-quality evidence. |
| OpenCode sidecar missing | Mark endpoint skipped with activation instructions. |
| Index timeout or transport closed | Record degraded context, use cached artifact if available, run the CLI-backed index receipt fallback when possible, and schedule index health repair. |
| Receipt missing or tampered | Emit `UNVERIFIABLE`, `DRIFT`, or typed escalation. |
| Schematic stale | Block release/promotion until graph is regenerated or drift is acknowledged. |
| Compute unavailable | Fall back to smaller local model, dry fixture, queued run, or explicit unavailable receipt. |
| Storage unavailable | Fall back to local filesystem store or block artifact-heavy runs with typed storage failure. |

## First implementation increment

Build in this order:

1. Shared schema package for run, event, receipt, model profile, tool profile, benchmark result, pubscan profile, compute profile, storage profile, and architecture graph.
2. File-backed local run/event/receipt store.
3. Pubscan tool-profile generator for `C:\dev\public\pubscan`.
4. Native rendering/tool profile and receipt adapter.
5. Compute and storage profile generators.
6. Worker wrapper around existing benchmark scripts and endpoint auth status script.
7. Object-store adapter for `C:\tmp` and project artifacts.
8. Optional FastAPI control-plane service with local SQLite/PostgreSQL adapter.
9. Optional rich UI shell with Dashboard, Runs, Benchmarks, Models, Tools, Receipts, Schematics, Settings.
10. Relay integration for run events.
11. Plexus integration for architecture graph generation and drift gates.
12. PostgreSQL migration and enterprise auth.
13. Model Foundry release flow for 14B and 32B.

Initial file-store command:

```powershell
python scripts/run_harness_file_store.py --store-root C:/tmp/harness_file_store --init --snapshot --out C:/tmp/harness_file_store_snapshot_20260709.json
```

Zero-dependency harness executable entrypoint:

```powershell
.\harness.cmd manifest --out C:/tmp/harness_executable_manifest.json --markdown-out C:/tmp/harness_executable_manifest.md --store-root C:/tmp/harness_file_store
```

```powershell
.\harness.cmd registry --out C:/tmp/harness_command_registry.html --summary-out C:/tmp/harness_command_registry.json --store-root C:/tmp/harness_file_store
```

```powershell
.\harness.cmd benchmarks --providers serve,codex,ollama,claude,opencode,dry --artifact-roots "C:/tmp;C:/dev/local-model/artifacts" --out C:/tmp/harness_benchmark_profile_manifest.json --markdown-out C:/tmp/harness_benchmark_profile_manifest.md --store-root C:/tmp/harness_file_store
```

```powershell
.\harness.cmd benchmark-coverage --profile C:/tmp/harness_benchmark_profile_manifest.json --artifacts "C:/tmp/m7_source_mined_store_seed_20260709.json;C:/tmp/m7_governed_store_seed_20260709.json;C:/tmp/unisonai_stateful_provider_matrix_store_seed_20260709.json;C:/tmp/model_endpoint_profiles_20260709.json;C:/tmp/model_release_readiness_20260709.json" --out C:/tmp/harness_benchmark_profile_coverage.json --markdown-out C:/tmp/harness_benchmark_profile_coverage.md --store-root C:/tmp/harness_file_store
```

```powershell
.\harness.cmd --print-command plan --out C:/tmp/harness_closed_loop_seed_plan.json
```

```powershell
.\harness.cmd seed --store-root C:/tmp/harness_file_store --artifact-dir C:/tmp/harness_closed_loop_seed --out C:/tmp/harness_closed_loop_seed.json --unisonai-repair-json
```

```powershell
.\harness.cmd outcome --input C:/tmp/harness_closed_loop_seed.json --out C:/tmp/harness_closed_loop_outcome.json --markdown-out C:/tmp/harness_closed_loop_outcome.md --store-root C:/tmp/harness_file_store
```

The executable entrypoint is a Windows command wrapper over `scripts/run_harness_cli.py`. It uses only Python stdlib and existing harness scripts. Use `--print-command` before any long-running benchmark command when you need to inspect the exact delegated command without executing it. Use `manifest` to emit a self-describing command/schema/evidence manifest and optional file-backed receipt. Use `registry` to emit a static local HTML command registry plus a machine-readable command/risk summary from that manifest. Use `benchmarks` to emit the weighted benchmark profile manifest, provider-role matrix, provider aliases, coverage units, and metadata-only existing artifact inventory. Use `benchmark-coverage` to compare the declared benchmark contract against observed scorecard artifacts and expose missing benchmark, provider role, case/scenario-unit, per-unit metric completeness, per-unit metric validity, and provider-by-unit evidence. Use `execution-matrix` to emit the non-executing dry/focused/full benchmark run order, commands, artifact paths, expected schemas, provider roles, and approval gates. Use `comparison` to synthesize Codex-vs-Flywheel deltas from existing scorecards without rerunning models. Use `classifier-friction` to run the prompt-layer guardrail/accountability benchmark and emit provider x mode x task receipts for the receipts-vs-guardrails thesis. Provider role normalization is centralized in `harness.provider_roles` and is now stamped into M7, UnisonAI, and classifier-friction scorecard rows as `provider_role` while preserving the raw provider selector. Manifest rows include delegated scripts, output schemas, default artifact paths, long-running-risk labels, and recommended validation slices.

Profile receipt ingest command:

```powershell
python scripts/run_harness_file_store.py --store-root C:/tmp/harness_file_store --receipt-json C:/tmp/pubscan_resource_profiles_20260709.json --receipt-kind pubscan_resource_profiles --receipt-verdict PROFILED --out C:/tmp/harness_file_store_pubscan_receipt_20260709.json
```

Direct pubscan/resource profile store-sink command:

```powershell
python scripts/run_pubscan_resource_profiles.py --out C:/tmp/pubscan_resource_profiles_20260709.json --markdown-out C:/tmp/pubscan_resource_profiles_20260709.md --store-root C:/tmp/harness_file_store
```

Direct endpoint-auth store-sink command:

```powershell
python scripts/run_endpoint_auth_status.py --out C:/tmp/harness_endpoint_auth_status_20260709.json --markdown-out C:/tmp/harness_endpoint_auth_status_20260709.md --store-root C:/tmp/harness_file_store
```

Context inventory store-sink command:

```powershell
python scripts/run_context_inventory.py --out C:/tmp/context_inventory_20260709.json --markdown-out C:/tmp/context_inventory_20260709.md --store-root C:/tmp/harness_file_store
```

Tool readiness store-sink command:

```powershell
python scripts/run_tool_readiness_receipts.py --tools index,forum,gather,crucible,telos,aleph,mneme,relay,plexus,pubscan --base-root C:/dev/public --tool-root aleph=C:/dev/aleph --out C:/tmp/tool_readiness_20260709.json --markdown-out C:/tmp/tool_readiness_20260709.md --store-root C:/tmp/harness_file_store
```

Tool enterprise hardening plan command:

```powershell
python scripts/run_tool_hardening_plan.py --readiness-artifact C:/tmp/tool_readiness_20260709.json --out C:/tmp/tool_hardening_plan_20260709.json --markdown-out C:/tmp/tool_hardening_plan_20260709.md --store-root C:/tmp/harness_file_store
```

Harness executable tool-hardening command:

```powershell
.\harness.cmd tool-hardening --readiness-artifact C:/tmp/tool_readiness_20260709.json --out C:/tmp/tool_hardening_plan_20260709.json --markdown-out C:/tmp/tool_hardening_plan_20260709.md --store-root C:/tmp/harness_file_store
```

If the readiness artifact is missing or unreadable, the hardening plan records `source_loaded=false`, preserves the load error, and cannot report `enterprise_ready_static=true`.

Model release readiness store-sink command:

```powershell
python scripts/run_model_release_readiness.py --models 14B,32B --base-root E:/local-model-run --artifact-roots "C:/dev/local-model/artifacts;C:/tmp" --endpoint-profile-artifacts C:/tmp/model_endpoint_profiles_20260709.json --endpoint-gate-artifacts C:/tmp/model_endpoint_gate_20260709.json --out C:/tmp/model_release_readiness_20260709.json --markdown-out C:/tmp/model_release_readiness_20260709.md --store-root C:/tmp/harness_file_store
```

Model naming and publication plan command:

```powershell
python scripts/run_model_publish_plan.py --release-readiness-artifact C:/tmp/model_release_readiness_20260709.json --name-prefix Flywheel-Local-Coder --out C:/tmp/model_publish_plan_20260709.json --markdown-out C:/tmp/model_publish_plan_20260709.md --store-root C:/tmp/harness_file_store
```

Harness executable model-publish command:

```powershell
.\harness.cmd model-publish --release-readiness-artifact C:/tmp/model_release_readiness_20260709.json --name-prefix Flywheel-Local-Coder --out C:/tmp/model_publish_plan_20260709.json --markdown-out C:/tmp/model_publish_plan_20260709.md --store-root C:/tmp/harness_file_store
```

The publish-plan command does not publish models. It emits candidate names, required artifacts, blockers, and `DO_NOT_PUBLISH` or `READY_TO_STAGE` status for operator-gated release decisions.

Model endpoint profile store-sink command:

```powershell
python scripts/run_model_endpoint_profiles.py --models 14B,32B --base-root E:/local-model-run --out C:/tmp/model_endpoint_profiles_20260709.json --markdown-out C:/tmp/model_endpoint_profiles_20260709.md --store-root C:/tmp/harness_file_store
```

When no shared `--serve-url` is passed, endpoint profiles use distinct local serve defaults: `14B` maps to `http://127.0.0.1:8765` and `32B` maps to `http://127.0.0.1:8767`. Override with `--serve-url-14b` or `--serve-url-32b` when a different launcher owns those ports.

Model endpoint gate command:

```powershell
python scripts/run_model_endpoint_gate.py --profile-artifact C:/tmp/model_endpoint_profiles_20260709.json --models 14B,32B --out C:/tmp/model_endpoint_gate_20260709.json --markdown-out C:/tmp/model_endpoint_gate_20260709.md --store-root C:/tmp/harness_file_store
```

By default, endpoint gate failures are recorded as partial evidence and the command exits `0` so the closed-loop seed can continue when local endpoints are offline. Add `--strict-exit` for release gates that must fail the process on unavailable health or generation rows.

The endpoint gate validates expected-vs-observed `model_ref`; a 14B process cannot satisfy the 32B release gate even if it is reachable and generating.

Executable endpoint gate command:

```powershell
.\harness.cmd endpoint-gate --profile-artifact C:/tmp/model_endpoint_profiles_20260709.json --models 14B,32B --out C:/tmp/model_endpoint_gate_20260709.json --markdown-out C:/tmp/model_endpoint_gate_20260709.md --store-root C:/tmp/harness_file_store
```

Gather readiness store-sink command:

```powershell
python scripts/run_gather_readiness.py --gather-root C:/dev/public/gather --config-roots C:/dev/local-model/configs --config-pattern "gather-*.json" --credential-vars GATHER_DISCORD_BOT_TOKEN,DISCORD_TOKEN --out C:/tmp/gather_readiness_20260709.json --markdown-out C:/tmp/gather_readiness_20260709.md --store-root C:/tmp/harness_file_store
```

Benchmark profile manifest store-sink command:

```powershell
python scripts/run_benchmark_profile_manifest.py --providers serve,codex,ollama,claude,opencode,dry --artifact-roots "C:/tmp;C:/dev/local-model/artifacts" --out C:/tmp/benchmark_profile_manifest_20260709.json --markdown-out C:/tmp/benchmark_profile_manifest_20260709.md --store-root C:/tmp/harness_file_store
```

The benchmark profile includes weighted metric dimensions, weighted dataset lanes, pressure variables, runnable seed suites, and planned full-suite stress matrices. The full-suite contract covers long-horizon closed-loop agentic workflows, cross-harness reproducibility, 14B/32B local resource pressure, and toolchain failure-recovery coverage before final experimental claims are made.

Benchmark profile coverage store-sink command:

```powershell
python scripts/run_benchmark_profile_coverage.py --profile C:/tmp/benchmark_profile_manifest_20260709.json --artifacts "C:/tmp/m7_source_mined_store_seed_20260709.json;C:/tmp/m7_governed_store_seed_20260709.json;C:/tmp/unisonai_stateful_provider_matrix_store_seed_20260709.json;C:/tmp/classifier_friction_benchmark.json;C:/tmp/model_endpoint_profiles_20260709.json;C:/tmp/model_endpoint_gate_20260709.json;C:/tmp/model_release_readiness_20260709.json" --out C:/tmp/benchmark_profile_coverage_20260709.json --markdown-out C:/tmp/benchmark_profile_coverage_20260709.md --store-root C:/tmp/harness_file_store
```

Benchmark coverage checks declared runnable benchmarks, provider roles, coverage units, unit metric completeness, unit metric validity, provider-by-unit evidence, dataset lanes, and pressure variables. Missing dataset lanes or pressure variables keep the coverage verdict partial, even when benchmark artifacts exist.

Benchmark execution matrix command:

```powershell
python scripts/run_benchmark_execution_matrix.py --providers serve,codex,ollama,claude,opencode,dry --run-id benchmark_matrix_20260709 --artifact-dir C:/tmp/harness_benchmark_matrix_20260709 --out C:/tmp/benchmark_execution_matrix_20260709.json --markdown-out C:/tmp/benchmark_execution_matrix_20260709.md --store-root C:/tmp/harness_file_store
```

Harness executable execution-matrix command:

```powershell
.\harness.cmd execution-matrix --providers serve,codex,ollama,claude,opencode,dry --artifact-dir C:/tmp/harness_benchmark_matrix_20260709 --out C:/tmp/benchmark_execution_matrix_20260709.json --markdown-out C:/tmp/benchmark_execution_matrix_20260709.md --store-root C:/tmp/harness_file_store
```

Agentic task manifest command:

```powershell
python scripts/run_agentic_task_set_manifest.py --task-set C:/dev/local-model/benchmarks/agentic-task-set-v1.json --adapter C:/dev/local-model/benchmarks/agentic-task-set-adapter-v1.json --provider-roles dry --out C:/tmp/agentic_task_manifest_20260709.json --markdown-out C:/tmp/agentic_task_manifest_20260709.md --store-root C:/tmp/harness_file_store
```

Harness executable agentic-tasks command:

```powershell
.\harness.cmd agentic-tasks --task-set C:/dev/local-model/benchmarks/agentic-task-set-v1.json --adapter C:/dev/local-model/benchmarks/agentic-task-set-adapter-v1.json --provider-roles dry --out C:/tmp/agentic_task_manifest_20260709.json --markdown-out C:/tmp/agentic_task_manifest_20260709.md --store-root C:/tmp/harness_file_store
```

The agentic task manifest command is metadata-only. It reads the custom task set and adapter contract, emits schema `harness.agentic-task-manifest/v1`, hashes the exact prompt bytes for every task, records planned artifact paths, and emits manifest-only `harness.agentic-task-scorecard/v1` dry rows with status `planned` and failure class `not_executed`. It does not call providers, probe endpoints, read model weights, run benchmarks, or claim task success.

Classifier-friction benchmark store-sink command:

```powershell
python scripts/run_classifier_friction_benchmark.py --providers dry,serve,codex --modes-to-test guardrail_on,guardrail_off,accountability_first --endpoint-model gpt-5.3-codex-spark --max-tasks 1 --out C:/tmp/classifier_friction_benchmark.json --markdown-out C:/tmp/classifier_friction_benchmark.md --store-root C:/tmp/harness_file_store
```

Harness executable classifier-friction command:

```powershell
.\harness.cmd classifier-friction --providers dry,serve,codex --modes-to-test guardrail_on,guardrail_off,accountability_first --endpoint-model gpt-5.3-codex-spark --max-tasks 1 --out C:/tmp/classifier_friction_benchmark.json --markdown-out C:/tmp/classifier_friction_benchmark.md --store-root C:/tmp/harness_file_store
```

Harness comparison report command:

```powershell
python scripts/run_harness_comparison_report.py --artifacts "C:/tmp/m7_source_mined_store_seed_20260709.json;C:/tmp/m7_governed_store_seed_20260709.json;C:/tmp/unisonai_stateful_provider_matrix_store_seed_20260709.json;C:/tmp/classifier_friction_benchmark.json;C:/tmp/model_endpoint_gate_20260709.json" --out C:/tmp/harness_comparison_report_20260709.json --markdown-out C:/tmp/harness_comparison_report_20260709.md --store-root C:/tmp/harness_file_store
```

Harness executable comparison command:

```powershell
.\harness.cmd comparison --artifacts "C:/tmp/m7_source_mined_store_seed_20260709.json;C:/tmp/m7_governed_store_seed_20260709.json;C:/tmp/unisonai_stateful_provider_matrix_store_seed_20260709.json;C:/tmp/classifier_friction_benchmark.json;C:/tmp/model_endpoint_gate_20260709.json" --out C:/tmp/harness_comparison_report_20260709.json --markdown-out C:/tmp/harness_comparison_report_20260709.md --store-root C:/tmp/harness_file_store
```

M7 source-mined benchmark store-sink command:

```powershell
python scripts/run_m7_eval.py --source-mined --source-mined-providers serve,codex --source-mined-max-cases 2 --out C:/tmp/m7_source_mined_store_seed_20260709.json --store-root C:/tmp/harness_file_store
```

M7 governed-agent benchmark store-sink command:

```powershell
python scripts/run_m7_eval.py --governed-agent --governed-providers serve,codex --governed-backend-max-scenarios 2 --out C:/tmp/m7_governed_store_seed_20260709.json --store-root C:/tmp/harness_file_store
```

UnisonAI stateful provider-matrix store-sink command:

```powershell
python scripts/run_unisonai_stateful_benchmark.py --providers dry,serve,ollama,codex,claude,opencode --repair-json --out C:/tmp/unisonai_stateful_provider_matrix_store_seed_20260709.json --markdown-out C:/tmp/unisonai_stateful_provider_matrix_store_seed_20260709.md --store-root C:/tmp/harness_file_store
```

Closed-loop orchestration dry-plan command:

```powershell
python scripts/run_closed_loop_benchmark_seed.py --dry-plan --out C:/tmp/harness_closed_loop_seed_plan_20260709.json
```

Closed-loop orchestration execution command:

```powershell
python scripts/run_closed_loop_benchmark_seed.py --store-root C:/tmp/harness_file_store --artifact-dir C:/tmp/harness_closed_loop_seed_20260709 --out C:/tmp/harness_closed_loop_seed_20260709.json --unisonai-repair-json
```

Closed-loop orchestration includes executable manifest, command registry, Forum route receipts, MCP tool health receipts, benchmark execution matrix, benchmark profile, agentic task manifest, embodied realtime multimodal plan, context inventory, tool readiness, tool hardening plan, model endpoint profiles, model endpoint gates, model release readiness, model publish plan, gather readiness, pubscan profiles, index fallback receipts, classifier-friction scorecards, M7 scorecards, UnisonAI scorecards, benchmark coverage, and harness comparison synthesis by default. Use `--skip-harness-manifest` only when the executable command/schema surface has already been receipted for the run. Use `--skip-harness-registry` only when the local command registry and command/risk summary have already been receipted for the run. Use `--skip-forum-route-receipts` only when routing prompt hashes and any observed route-frame metadata have already been receipted for the run. Use `--skip-mcp-tool-health` only when configured tool roots and any observed MCP/tool statuses have already been receipted for the run. Use `--skip-benchmark-execution-matrix` only when the dry/focused/full benchmark run matrix and evidence gates have already been receipted for the run. Use `--skip-benchmark-profile` only when the benchmark contract, metric weights, provider matrix, and existing artifact inventory have already been receipted for the run. Use `--skip-agentic-task-manifest` only when custom task prompt hashes, planned artifacts, and dry/null scorecard rows have already been receipted for the run. Use `--skip-embodied-realtime` only when embodied realtime planned probes, prompt hashes, model-lead verification gaps, and dry scorecard placeholder rows have already been receipted for the run. Use `--skip-benchmark-coverage` only when declared-vs-observed benchmark/provider coverage has already been receipted for the run. Use `--skip-harness-comparison` only when Codex-vs-Flywheel comparison synthesis has already been receipted for the run. Use `--skip-context-inventory` only when the scratch/session context shape has already been captured for the run. Use `--skip-tool-readiness` only when the full flagship/pubscan static readiness set has already been receipted for the run. Use `--skip-tool-hardening-plan` only when the mneme/relay/plexus hardening action plan has already been receipted for the run. Use `--skip-model-endpoint-profiles` only when 14B/32B endpoint profile receipts have already been captured for the run. Use `--skip-model-endpoint-gate` only when 14B/32B endpoint health/generation gate receipts have already been captured for the run. Use `--skip-model-release-readiness` only when 14B/32B release readiness has already been receipted for the run. Use `--skip-model-publish-plan` only when the 14B/32B naming and publication plan has already been receipted for the run. Use `--skip-gather-readiness` only when gather/source-intake readiness has already been receipted for the run. Use `--skip-classifier-friction` only when the guardrail/accountability friction lane has already been receipted for the run.

Executable wrappers for the two newest metadata preflights:

```powershell
.\harness.cmd forum-route --route "Route the active Codex/Flywheel local-model objective." --out C:/tmp/forum_route_receipts.json --markdown-out C:/tmp/forum_route_receipts.md --store-root C:/tmp/harness_file_store
.\harness.cmd mcp-health --tools index,forum,telos,gather,crucible,aleph,mneme,relay,plexus,pubscan,local-model --observation "index=TRANSPORT_CLOSED|transport_closed|Transport closed" --out C:/tmp/mcp_tool_health.json --markdown-out C:/tmp/mcp_tool_health.md --store-root C:/tmp/harness_file_store
```

Closed-loop outcome synthesis command:

```powershell
python scripts/run_closed_loop_outcome_report.py --input C:/tmp/harness_closed_loop_seed_20260709.json --out C:/tmp/harness_closed_loop_outcome_20260709.json --markdown-out C:/tmp/harness_closed_loop_outcome_20260709.md --store-root C:/tmp/harness_file_store
```

Closed-loop outcome synthesis from store run id:

```powershell
python scripts/run_closed_loop_outcome_report.py --store-root C:/tmp/harness_file_store --run-id <run_id> --out C:/tmp/harness_closed_loop_outcome_20260709.json --markdown-out C:/tmp/harness_closed_loop_outcome_20260709.md
```

Outcome synthesis behavior:

- Parses child JSON artifacts referenced by the closed-loop seed report when they exist.
- Extracts executable command/schema/evidence signals from `harness.executable-manifest/v1` artifacts when present.
- Extracts Codex-vs-Flywheel comparison signals from `harness.comparison-report/v1` artifacts when present.
- Extracts local command registry command/risk signals from `harness.command-registry-html/v1` summary artifacts when present.
- Extracts benchmark contract signals from `harness.benchmark-profile-manifest/v1` artifacts when present.
- Extracts benchmark execution matrix signals from `harness.benchmark-execution-matrix/v1` artifacts when present.
- Extracts planned custom task coverage from `harness.agentic-task-manifest/v1` artifacts when present.
- Extracts declared-vs-observed benchmark/provider-role/unit coverage, provider alias maps, per-unit metric completeness, per-unit metric validity, and provider-by-unit evidence from `harness.benchmark-profile-coverage/v1` artifacts when present.
- Extracts context inventory signals from `harness.context-inventory/v1` artifacts when present.
- Extracts full flagship/pubscan static readiness signals from `harness.tool-readiness/v1` artifacts when present.
- Extracts mneme/relay/plexus hardening-plan signals from `harness.tool-hardening-plan/v1` artifacts when present.
- Extracts local 14B/32B endpoint profile signals from `harness.model-endpoint-profiles/v1` artifacts when present.
- Extracts 14B/32B static model release readiness signals from `harness.model-release-readiness/v1` artifacts when present.
- Extracts 14B/32B candidate naming and publication blocker signals from `harness.model-publish-plan/v1` artifacts when present.
- Extracts gather/source-intake readiness signals from `harness.gather-readiness/v1` artifacts when present.
- Extracts M7 source-mined comparisons, M7 governed-agent comparisons, and UnisonAI provider-matrix rows.
- Keeps missing, unreadable, or non-JSON child artifacts as explicit observations rather than inventing benchmark conclusions.
- Can locate the closed-loop seed report from `artifacts.jsonl` using `--store-root` plus `--run-id` when the report was stored with label `closed-loop-seed-report-json`.

Index MCP fallback receipt command:

```powershell
python scripts/run_index_receipt.py --lane context-envelope --root C:/dev/local-model --index-root C:/dev/public/index --budget 12000 --focus local-model --hops 2 --mcp-tool index_context_envelope --mcp-status transport_closed --mcp-error-code transport_closed --mcp-error-summary "Transport closed" --artifact-out C:/tmp/index_context_envelope_fallback_20260709.json --out C:/tmp/index_context_envelope_fallback_receipt_20260709.json --store-root C:/tmp/harness_file_store
```

Index fallback health behavior:

- The command reads the previous `--artifact-out` before running Index. If the fresh CLI run times out, exits nonzero, emits empty output, or emits invalid JSON, and the previous artifact is still valid for the lane, the receipt returns `DEGRADED_MATCH` with `effective_output_source=stale_artifact`.
- Live failure evidence remains in `live_verdict`, `live_failure_code`, stdout/stderr hashes, byte counts, and elapsed time. The stale artifact is preserved instead of overwritten when degraded fallback is used.
- Use `--stale-artifact` to point at a specific last-known-good context artifact instead of reusing `--artifact-out`.

Index router fallback receipt command:

```powershell
python scripts/run_index_receipt.py --lane router --root C:/dev --index-root C:/dev/public/index --max-docs 500 --artifact-out C:/tmp/index_router_fallback_20260709.md --out C:/tmp/index_router_fallback_receipt_20260709.json --store-root C:/tmp/harness_file_store
```

Current limitation:

- The file-store, executable front-controller, manifest, command registry, benchmark profile, benchmark coverage, direct store-sink, context inventory, expanded tool readiness, model release readiness, gather readiness, benchmark store-sink, closed-loop orchestration, outcome synthesis, and index fallback commands and tests have been added but not executed in this slice because validation/probe execution requires explicit user approval in this session.
- File-backed local-core storage now includes `artifacts.jsonl` for queryable artifact rows, but no SQL/PostgreSQL adapter has been implemented yet.

## 2026-07-09 update: planned task coverage semantics

- Benchmark coverage treats `harness.agentic-task-manifest/v1` as a planning artifact only. It is useful for verifying intended coverage shape before execution, but it does not satisfy missing runnable benchmarks, unit metrics, provider-unit metrics, dataset-lane coverage, or pressure-variable coverage.
- Closed-loop outcome synthesis records task-manifest signals under `agentic_task_manifest_signals`, separate from `benchmark_signals`, so experimental outcomes keep plan evidence and executed scorecards distinct.
- Forum ledger scaling feedback is now represented as a benchmark contract at `C:/dev/local-model/benchmarks/forum-ledger-deep-verify-scaling-v1.json`.

## 2026-07-09 update: Index MCP and realtime multimodal benchmark contracts

- Index MCP transport hardening now exists in the local `C:/dev/public/index` checkout. Tool failures are intended to surface as `index.mcp-tool-error/v1` with `UNVERIFIABLE` instead of opaque transport closure when the failure is catchable by Python.
- The benchmark profile now includes two additional full-suite planned benchmarks: `forum_ledger_deep_verify_scaling` and `embodied_realtime_multimodal_pressure`.
- The embodied realtime lane is scoped to small/local model robotics-style usefulness, code-rendered spatial reasoning, simplified sensor streams, model-card verification, and benign affective drift probes. Named model leads from external feedback are recorded as unverified until model cards are checked.

## Embodied realtime multimodal plan command

```powershell
.\harness.cmd embodied-realtime --contract C:/dev/local-model/benchmarks/embodied-realtime-multimodal-v1.json --providers dry,codex --latency-budgets-ms 250,500,1000 --artifact-dir C:/tmp/embodied_realtime_multimodal --out C:/tmp/embodied_realtime_multimodal_plan.json --markdown-out C:/tmp/embodied_realtime_multimodal_plan.md --store-root C:/tmp/harness_file_store
```

This command is metadata-only. It emits schema `harness.embodied-realtime-multimodal/v1`, planned probe rows, prompt hashes, expected artifacts, and dry scorecard rows. It does not call providers, verify model cards, execute code-rendering checks, probe endpoints, or score model quality. Coverage and outcome reports ingest it as planned-only evidence.

Closed-loop wiring update:

- `run_closed_loop_benchmark_seed.py` now includes `embodied_realtime_multimodal_plan` by default after the agentic task manifest and before context inventory, with `--skip-embodied-realtime` for runs that already receipted that plan.
- `run_benchmark_execution_matrix.py` now includes dry-tier `embodied_realtime_plan` and feeds `embodied_realtime_multimodal_plan.json` into downstream coverage/comparison artifact lists.
- This wiring still does not execute models, endpoints, sensors, renderers, or model-card verification. It only makes the planned embodied realtime lane visible to closed-loop dry plans, coverage, and outcome synthesis.

## 2026-07-09 update: cross-harness manifest command and seed wiring

Cross-harness manifest command:

```powershell
python scripts/run_cross_harness_manifest.py --task-set C:/dev/local-model/benchmarks/agentic-task-set-v1.json --contract C:/dev/local-model/benchmarks/cross-harness-adapter-contract-v1.json --provider-roles codex_harness,flywheel_harness,claude_code,opencode,local_14b,local_32b,dry --out C:/tmp/cross_harness_manifest_20260709.json --markdown-out C:/tmp/cross_harness_manifest_20260709.md --store-root C:/tmp/harness_file_store
```

Executable wrapper:

```powershell
.\harness.cmd cross-harness --task-set C:/dev/local-model/benchmarks/agentic-task-set-v1.json --contract C:/dev/local-model/benchmarks/cross-harness-adapter-contract-v1.json --provider-roles codex_harness,flywheel_harness,claude_code,opencode,local_14b,local_32b,dry --out C:/tmp/cross_harness_manifest_20260709.json --markdown-out C:/tmp/cross_harness_manifest_20260709.md --store-root C:/tmp/harness_file_store
```

The cross-harness manifest command is metadata-only. It emits schema `harness.cross-harness-manifest/v1`, shared task prompt hashes, planned artifact paths, provider-role rows, required receipt expectations, and manifest-only `harness.cross-harness-task-scorecard/v1` rows. It does not call Codex, Flywheel, Claude Code, OpenCode, local endpoints, model weights, or benchmark runners.

Closed-loop wiring:

- `run_closed_loop_benchmark_seed.py` now includes `cross_harness_manifest` by default after `agentic_task_manifest`, with `--skip-cross-harness-manifest` for already-receipted runs.
- `run_benchmark_execution_matrix.py` now includes dry-tier `cross_harness_manifest` with expected schemas `harness.cross-harness-manifest/v1` and `harness.cross-harness-task-scorecard/v1`.
- `run_benchmark_profile_coverage.py` and `run_closed_loop_outcome_report.py` ingest cross-harness manifests as planned-only evidence, separate from executed comparison results.

## 2026-07-09 update: schematic drift command

Schematic drift command:

```powershell
python scripts/run_schematic_drift_check.py --graph C:/dev/local-model/project-docs/schematics/closed-loop-integration.graph.json --report C:/dev/local-model/project-docs/records/CLOSED-LOOP-INTEGRATION-SCHEMATIC-2026-07-09.md --out C:/tmp/schematic_drift_check_20260709.json --markdown-out C:/tmp/schematic_drift_check_20260709.md --store-root C:/tmp/harness_file_store
```

Executable wrapper:

```powershell
.\harness.cmd schematic-drift --graph C:/dev/local-model/project-docs/schematics/closed-loop-integration.graph.json --report C:/dev/local-model/project-docs/records/CLOSED-LOOP-INTEGRATION-SCHEMATIC-2026-07-09.md --out C:/tmp/schematic_drift_check_20260709.json --markdown-out C:/tmp/schematic_drift_check_20260709.md --store-root C:/tmp/harness_file_store
```

The schematic drift command is metadata-only. It emits schema `harness.schematic-drift-check/v1`, checks required graph nodes, required edges, referenced local files, and known stale prose markers, and records non-execution guards. It does not run tests, benchmarks, endpoints, providers, or model weights.
