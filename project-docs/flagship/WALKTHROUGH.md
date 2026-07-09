# Flagship operator walkthrough

## 1. Build the package

```powershell
python scripts/build_local_harness_exes.py --skip-serve --package --package-version dev-local
```

Use `--skip-serve` for the normal lightweight package. The core harness delegates model serving to the local runtime and endpoint profiles.

## 2. Inspect the executable surface

```powershell
artifacts\exe\local-harness.cmd manifest
```

This lists the packaged command surface and confirms the harness can locate the source checkout through `LOCAL_HARNESS_REPO`.

## 3. Inspect local model wiring

Open these packaged receipts:

- `artifacts/exe/model_endpoint_profiles.local.json`
- `artifacts/exe/model_release_readiness.local.json`
- `artifacts/exe/model_publish_plan.local.json`
- `artifacts/exe/huggingface_release_stage.local.json`

The default local endpoints are `http://127.0.0.1:8765` for 14B and `http://127.0.0.1:8768` for 32B.

## 4. Inspect tools

Open:

- `artifacts/exe/tool_integration_contract.local.json`
- `artifacts/exe/tool_readiness.local.json`
- `artifacts/exe/tool_hardening_plan.local.json`
- `artifacts/exe/tool_operator_guide.local.md`

The operator guide is the concise runbook for each packaged tool.

## 5. Gate release

```powershell
python scripts/run_package_ship_doctor.py --package-summary artifacts/exe/packages/local-harness-dev-local.package.json --strict-exit
```

Ship the harness package only when the doctor is `SHIP_READY`.
Upload models only when Hugging Face staging says `READY_TO_UPLOAD` and the operator has approved the upload.
