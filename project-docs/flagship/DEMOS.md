# Flagship demos

These demos are designed for a local, offline-first walkthrough. They avoid hosted dependencies and do not publish models.

## Demo 1: package inspection

```powershell
python scripts/build_local_harness_exes.py --skip-serve --package --package-version dev-local
python scripts/run_package_ship_doctor.py --package-summary artifacts/exe/packages/local-harness-dev-local.package.json --strict-exit
```

Shows the package doctor, required files, schema checks, zip integrity, model endpoint coverage, and no-secret posture.

## Demo 2: tool fabric receipt loop

```powershell
python scripts/run_tool_readiness_receipts.py --tools index,forum,gather,crucible,telos,aleph,mneme,relay,plexus,pubscan,local-model --base-root C:/dev/public --tool-root aleph=C:/dev/aleph --tool-root local-model=C:/dev/local-model
python scripts/run_tool_operator_guide.py --tool-contract artifacts/exe/tool_integration_contract.local.json
```

Shows what each tool does, where it lives, how it is operated, and what remains blocked before enterprise release.

## Demo 3: local model release staging

```powershell
python scripts/run_huggingface_release_stage.py --release-readiness-artifact artifacts/exe/model_release_readiness.local.json --publish-plan-artifact artifacts/exe/model_publish_plan.local.json --namespace HarperZ9
```

Shows the proposed Hugging Face repo IDs and upload commands while keeping upload disabled until release gates pass.

## Demo 4: architecture receipt

```powershell
python scripts/run_harness_architecture_report.py --dist artifacts/exe --package-doctor artifacts/exe/packages/local-harness-dev-local.doctor.json
```

Shows the executable surface, context map, pubscan resources, local endpoints, tool fabric, model release status, and next gates.
