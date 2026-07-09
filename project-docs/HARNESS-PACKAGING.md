# Harness packaging

This package path makes the full local harness executable before benchmark comparison work.

## Build

```powershell
python scripts/build_local_harness_exes.py --skip-serve --package --package-version dev-local
```

`--skip-serve` keeps the packaged harness light. Local model serving remains wired through the configured local Python runtime and endpoint profiles.

## Artifacts

- `artifacts/exe/local-harness.exe`: full `harness.cmd` command surface.
- `artifacts/exe/local-harness.cmd`: wrapper that sets `LOCAL_HARNESS_REPO` when the artifact remains under the checkout.
- `artifacts/exe/local-agent.exe`: offline/local agent entrypoint.
- `artifacts/exe/model_endpoint_profiles.local.json`: generated 14B/32B endpoint profile artifact.
- `artifacts/exe/model_release_readiness.local.json`: 14B/32B static model release-readiness receipt.
- `artifacts/exe/model_publish_plan.local.json`: 14B/32B naming and publication plan.
- `artifacts/exe/tool_integration_contract.local.json`: packaged tool sidecar contract for index, forum, gather, crucible, telos, aleph, mneme, relay, plexus, pubscan, and local-model.
- `artifacts/exe/tool_readiness.local.json`: metadata-only static readiness receipt for flagship and sidecar tools.
- `artifacts/exe/tool_hardening_plan.local.json`: enterprise hardening action and release-gate plan generated from tool readiness.
- `artifacts/exe/runtime_activation_contract.local.json`: packaged runtime activation contract for storage, env knobs, sidecars, and launch boundaries.
- `artifacts/exe/codex_mcp_launch_contract.local.json`: Codex MCP launch, stale-transport reload, and direct CLI fallback contract.
- `artifacts/exe/context_inventory.local.json`: metadata-only workspace context map for scratch, temp, session, and benchmark surfaces.
- `artifacts/exe/context_inventory.local.md`: human-readable workspace context inventory.
- `artifacts/exe/pubscan_resource_profiles.local.json`: zero-dependency pubscan, native-rendering, compute, and storage capability profiles.
- `artifacts/exe/pubscan_resource_profiles.local.md`: human-readable pubscan/resource profile report.
- `artifacts/exe/harness_executable_manifest.local.json`: packaged command-surface manifest.
- `artifacts/exe/harness_architecture_report.local.json`: harness architecture and endpoint report stitched from generated contracts.
- `artifacts/exe/enterprise_readiness_report.local.json`: mneme, relay, and plexus enterprise-readiness gates derived from the tool contract.
- `artifacts/exe/local-harness-release.json`: release manifest for the local executable package.
- `artifacts/exe/packages/local-harness-<version>.zip`: shippable release bundle.
- `artifacts/exe/packages/local-harness-<version>.package.json`: sidecar package summary with outer zip hash.
- `artifacts/exe/packages/local-harness-<version>.doctor.json`: release doctor verdict for required files, schemas, zip hash, local model profile coverage, and no-secret posture.
- `artifacts/exe/packages/local-harness-<version>.doctor.md`: human-readable release doctor summary.
- `artifacts/exe/packages/local-harness-<version>.architecture.json`: post-package architecture report including release doctor status.
- `artifacts/exe/packages/local-harness-<version>.architecture.md`: human-readable post-package architecture report.
- `artifacts/exe/packages/local-harness-<version>/manifest/ship-manifest.json`: file hashes, source commit, dependency posture, and secret policy.

## Local model wiring

The package emits default local endpoint profiles:

- `14B`: `http://127.0.0.1:8765`
- `32B`: `http://127.0.0.1:8768`
- `32B runtime`: `cpu-offload`
- serve Python: `E:/local-model-run/venv/Scripts/python.exe`

The full harness executable still delegates long-running local model serving to the local runtime instead of embedding model weights or the Torch stack into the core harness executable.

## Ship bundle contents

The release bundle includes:

- `bin/local-harness.exe`
- `bin/local-harness.cmd`
- `bin/local-agent.exe`
- `config/model_endpoint_profiles.local.json`
- `config/model_endpoint_profiles.local.md`
- `config/model_release_readiness.local.json`
- `docs/model_release_readiness.local.md`
- `config/model_publish_plan.local.json`
- `docs/model_publish_plan.local.md`
- `config/tool_integration_contract.local.json`
- `config/tool_integration_contract.local.md`
- `config/runtime_activation_contract.local.json`
- `config/runtime_activation_contract.local.md`
- `config/codex_mcp_launch_contract.local.json`
- `config/codex_mcp_launch_contract.local.md`
- `config/harness_architecture_report.local.json`
- `config/enterprise_readiness_report.local.json`
- `docs/harness_architecture_report.local.md`
- `docs/enterprise_readiness_report.local.md`
- `manifest/harness_executable_manifest.local.json`
- `manifest/harness_executable_manifest.local.md`
- `docs/HARNESS-PACKAGING.md`
- `manifest/local-harness-release.json`
- `manifest/ship-manifest.json`
- `SHA256SUMS.txt`

The bundle excludes model weights, `.env` files, credentials, tokens, private keys, caches, benchmark outputs, and user corpora.
