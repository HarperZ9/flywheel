# Harness packaging

This package path makes the full local harness executable before benchmark comparison work.

## Build

```powershell
python scripts/build_local_harness_exes.py --skip-serve
```

`--skip-serve` keeps the packaged harness light. Local model serving remains wired through the configured local Python runtime and endpoint profiles.

## Artifacts

- `artifacts/exe/local-harness.exe`: full `harness.cmd` command surface.
- `artifacts/exe/local-harness.cmd`: wrapper that sets `LOCAL_HARNESS_REPO` when the artifact remains under the checkout.
- `artifacts/exe/local-agent.exe`: offline/local agent entrypoint.
- `artifacts/exe/model_endpoint_profiles.local.json`: generated 14B/32B endpoint profile artifact.
- `artifacts/exe/local-harness-release.json`: release manifest for the local executable package.

## Local model wiring

The package emits default local endpoint profiles:

- `14B`: `http://127.0.0.1:8765`
- `32B`: `http://127.0.0.1:8768`
- `32B runtime`: `cpu-offload`
- serve Python: `E:/local-model-run/venv/Scripts/python.exe`

The full harness executable still delegates long-running local model serving to the local runtime instead of embedding model weights or the Torch stack into the core harness executable.
