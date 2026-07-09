"""Emit the packaged runtime activation contract for the local harness."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.file_backed_store import FileBackedHarnessStore  # noqa: E402

DEFAULT_ENV_VARS = [
    "LOCAL_HARNESS_REPO",
    "LOCAL_SERVE_PYTHON",
    "LOCAL_SERVE_REPO",
    "OLLAMA_HOST",
    "SERVE_MODEL_ALIAS",
    "SERVE_MODEL_PATH",
    "SERVE_MODEL_REF",
    "SERVE_ADAPTER_PATH",
    "SERVE_PORT",
    "SERVE_DEVICE_MAP",
    "SERVE_MAX_MEMORY_GPU",
    "SERVE_MAX_MEMORY_CPU",
    "SERVE_OFFLOAD_FOLDER",
]


def now_utc() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def split_names(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def path_row(name: str, path: Path, *, purpose: str, required: bool) -> dict[str, Any]:
    expanded = path.expanduser()
    return {
        "schema": "harness.runtime-activation.path/v1",
        "name": name,
        "path": str(expanded),
        "exists": expanded.exists(),
        "required": required,
        "purpose": purpose,
    }


def env_rows(names: list[str]) -> list[dict[str, Any]]:
    rows = []
    for name in names:
        value = os.environ.get(name, "")
        rows.append(
            {
                "schema": "harness.runtime-activation.env/v1",
                "name": name,
                "present": bool(value),
                "value_recorded": False,
                "purpose": env_purpose(name),
            }
        )
    return rows


def env_purpose(name: str) -> str:
    purposes = {
        "LOCAL_HARNESS_REPO": "repo checkout used by the packaged local-harness wrapper",
        "LOCAL_SERVE_PYTHON": "local Python runtime used for Torch-backed model serving",
        "LOCAL_SERVE_REPO": "repo checkout used by the optional local-serve wrapper",
        "OLLAMA_HOST": "optional Ollama endpoint host",
        "SERVE_MODEL_ALIAS": "optional serve.py model selector",
        "SERVE_MODEL_PATH": "optional explicit local model root",
        "SERVE_MODEL_REF": "non-secret model reference string",
        "SERVE_ADAPTER_PATH": "optional adapter path",
        "SERVE_PORT": "serve.py HTTP port",
        "SERVE_DEVICE_MAP": "Torch/Transformers device-map strategy",
        "SERVE_MAX_MEMORY_GPU": "offload GPU memory cap",
        "SERVE_MAX_MEMORY_CPU": "offload CPU memory cap",
        "SERVE_OFFLOAD_FOLDER": "offload state folder",
    }
    return purposes.get(name, "runtime configuration knob")


def build_contract(
    *,
    package_root: Path,
    repo_root: Path,
    store_root: Path,
    model_run_root: Path,
    log_root: Path,
    env_vars: list[str],
) -> dict[str, Any]:
    config_root = package_root / "config" if (package_root / "config").exists() else package_root
    package_paths = [
        path_row("package_root", package_root, purpose="release artifact root containing bin/config/docs/manifest", required=True),
        path_row("repo_root", repo_root, purpose="source checkout used by sidecar scripts and tool contracts", required=True),
        path_row("local_harness_exe", package_root / "local-harness.exe", purpose="full local harness executable", required=False),
        path_row("local_harness_cmd", package_root / "local-harness.cmd", purpose="wrapper that sets LOCAL_HARNESS_REPO when inside checkout", required=False),
        path_row("package_bin_harness", package_root / "bin" / "local-harness.exe", purpose="bundled harness executable when inspecting extracted zip", required=False),
        path_row("endpoint_profiles", config_root / "model_endpoint_profiles.local.json", purpose="14B/32B local endpoint profile contract", required=True),
        path_row("tool_contract", config_root / "tool_integration_contract.local.json", purpose="Flywheel/Codex sidecar tool contract", required=True),
        path_row("runtime_contract", config_root / "runtime_activation_contract.local.json", purpose="this runtime activation contract when packaged", required=False),
    ]
    storage_paths = [
        path_row("store_root", store_root, purpose="file-backed receipt and artifact store", required=False),
        path_row("receipt_bodies", store_root / "receipt-bodies", purpose="content-addressed receipt bodies", required=False),
        path_row("artifacts", store_root / "artifacts", purpose="copied generated artifacts", required=False),
        path_row("local_model_run_root", model_run_root, purpose="external model weights/runtime root; not packaged", required=True),
        path_row("model_offload_root", model_run_root / "offload", purpose="external CPU/GPU offload state", required=False),
        path_row("serve_log_root", log_root, purpose="local serve-launch log directory", required=False),
    ]
    env = env_rows(env_vars)
    required_paths_missing = [
        row["name"] for row in package_paths + storage_paths if row["required"] and not row["exists"]
    ]
    return {
        "schema": "harness.runtime-activation-contract/v1",
        "created_utc": now_utc(),
        "dependency_posture": "metadata-only runtime contract; no benchmarks, provider calls, endpoint probes, token stores, source bodies, or model weights are read",
        "secret_policy": "environment values are not recorded; only presence booleans and non-secret path contracts are emitted",
        "package": {
            "root": str(package_root),
            "paths": package_paths,
        },
        "storage": {
            "paths": storage_paths,
            "persistence_model": "append-only/file-backed receipts plus copied artifacts; model weights and offload state remain external",
        },
        "environment": {
            "vars": env,
            "present": sum(1 for row in env if row["present"]),
            "checked": len(env),
        },
        "activation_steps": [
            "Set LOCAL_HARNESS_REPO if the extracted package is not under the source checkout.",
            "Run bin/local-harness.cmd manifest to inspect command surface.",
            "Run bin/local-harness.cmd tool-contract to inspect sidecar tool wiring.",
            "Run bin/local-harness.cmd readiness model-endpoints with the packaged endpoint defaults.",
            "Run bin/local-harness.cmd serve-resource before starting local model endpoints.",
            "Run bin/local-harness.cmd serve-launch only when intentionally starting local model serve processes.",
        ],
        "runtime_boundaries": [
            "No hosted service is required for package inspection.",
            "Model weights are not packaged.",
            "Secrets and .env files are not packaged.",
            "Sidecar tools remain external roots and are represented by contracts and receipts.",
            "Benchmarks are intentionally outside this runtime activation contract.",
        ],
        "summary": {
            "package_paths": len(package_paths),
            "storage_paths": len(storage_paths),
            "required_paths_missing": required_paths_missing,
            "required_paths_missing_count": len(required_paths_missing),
            "env_vars_checked": len(env),
            "env_vars_present": sum(1 for row in env if row["present"]),
            "ready_for_package_inspection": len(required_paths_missing) == 0,
        },
    }


def render_markdown(contract: dict[str, Any]) -> str:
    summary = contract["summary"]
    lines = [
        "# Runtime activation contract",
        "",
        f"- Schema: `{contract['schema']}`",
        f"- Created UTC: `{contract['created_utc']}`",
        f"- Dependency posture: {contract['dependency_posture']}",
        f"- Secret policy: {contract['secret_policy']}",
        f"- Ready for package inspection: `{str(summary['ready_for_package_inspection']).lower()}`",
        f"- Required paths missing: `{summary['required_paths_missing_count']}`",
        f"- Env vars present: `{summary['env_vars_present']}` / `{summary['env_vars_checked']}`",
        "",
        "## Required path posture",
        "",
        "| Name | Exists | Required | Purpose |",
        "|---|---:|---:|---|",
    ]
    for row in contract["package"]["paths"] + contract["storage"]["paths"]:
        if row["required"]:
            lines.append(f"| {row['name']} | {str(row['exists']).lower()} | {str(row['required']).lower()} | {row['purpose']} |")
    lines.extend(["", "## Activation steps", ""])
    for step in contract["activation_steps"]:
        lines.append(f"- {step}")
    lines.extend(["", "## Runtime boundaries", ""])
    for boundary in contract["runtime_boundaries"]:
        lines.append(f"- {boundary}")
    return "\n".join(lines) + "\n"


def _write(path_text: str, text: str) -> str:
    if not path_text:
        return ""
    path = Path(path_text)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return str(path)


def _store_outputs(contract: dict[str, Any], *, store_root: str, run_id: str, artifacts: list[tuple[str, str]]) -> list[dict[str, Any]]:
    if not store_root:
        return []
    store = FileBackedHarnessStore(Path(store_root))
    verdict = "RUNTIME_CONTRACT_READY" if contract["summary"]["ready_for_package_inspection"] else "RUNTIME_CONTRACT_INCOMPLETE"
    outputs = [store.put_receipt(kind="runtime_activation_contract", body=contract, run_id=run_id, verdict=verdict)]
    for path_text, label in artifacts:
        if path_text and Path(path_text).exists():
            outputs.append(store.copy_artifact(Path(path_text), run_id=run_id, label=label))
    return outputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-root", default="C:/dev/local-model/artifacts/exe")
    parser.add_argument("--repo-root", default="C:/dev/local-model")
    parser.add_argument("--store-root", default="C:/tmp/harness_file_store")
    parser.add_argument("--model-run-root", default="E:/local-model-run")
    parser.add_argument("--log-root", default="C:/tmp/local_model_serve_logs")
    parser.add_argument("--env-vars", default=",".join(DEFAULT_ENV_VARS))
    parser.add_argument("--out", default="")
    parser.add_argument("--markdown-out", default="")
    parser.add_argument("--run-id", default="")
    args = parser.parse_args(argv)

    contract = build_contract(
        package_root=Path(args.package_root),
        repo_root=Path(args.repo_root),
        store_root=Path(args.store_root),
        model_run_root=Path(args.model_run_root),
        log_root=Path(args.log_root),
        env_vars=split_names(args.env_vars),
    )
    json_text = json.dumps(contract, indent=2, sort_keys=True)
    md_text = render_markdown(contract)
    json_path = _write(args.out, json_text)
    md_path = _write(args.markdown_out, md_text)
    store_outputs = _store_outputs(
        contract,
        store_root=args.store_root,
        run_id=args.run_id,
        artifacts=[
            (json_path, "runtime-activation-contract-json"),
            (md_path, "runtime-activation-contract-markdown"),
        ],
    )
    if store_outputs:
        contract = {**contract, "store_outputs": store_outputs}
        json_text = json.dumps(contract, indent=2, sort_keys=True)
    print(json_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
