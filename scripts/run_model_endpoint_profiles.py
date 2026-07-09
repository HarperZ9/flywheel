"""Emit metadata-only endpoint profiles for local 14B/32B agentic workflows."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.file_backed_store import FileBackedHarnessStore  # noqa: E402
from harness.model_profiles import candidate_model_roots, model_key, model_profile  # noqa: E402
from harness.provider_roles import provider_role  # noqa: E402

DEFAULT_SERVE_URLS = {
    "14b": "http://127.0.0.1:8765",
    "32b": "http://127.0.0.1:8767",
}

RUNTIME_STRATEGIES = {
    "cpu-offload": {
        "device_map": "auto",
        "max_memory_gpu": "20GiB",
        "max_memory_cpu": "96GiB",
        "offload_folder_template": "E:/local-model-run/offload/{model_key}",
    },
}


def now_utc() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def split_names(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _pick_root(model: str, base_root: Path) -> tuple[Path, list[str]]:
    candidates = candidate_model_roots(model, base_root)
    for path in candidates:
        if path.exists():
            return path, [str(item) for item in candidates]
    return candidates[0], [str(item) for item in candidates]


def _serve_url_for_model(model: str, *, serve_url: str, serve_urls: dict[str, str]) -> str:
    key = model_key(model)
    explicit = serve_urls.get(key, "").strip()
    if explicit:
        return explicit.rstrip("/")
    shared = serve_url.strip()
    if shared:
        return shared.rstrip("/")
    return DEFAULT_SERVE_URLS.get(key, DEFAULT_SERVE_URLS["14b"])


def _endpoint_port(endpoint_url: str, fallback: int = 8765) -> int:
    parsed = urlparse(endpoint_url)
    return int(parsed.port or fallback)


def _runtime_config(model: str, strategy: str) -> dict[str, Any]:
    name = strategy.strip().lower()
    if not name:
        return {"strategy": "gpu-single", "serve_args": [], "requires_offload": False}
    spec = RUNTIME_STRATEGIES.get(name, {})
    if not spec:
        return {"strategy": name, "serve_args": [], "requires_offload": False}
    folder = spec["offload_folder_template"].format(model_key=model_key(model))
    serve_args = [
        "--device-map",
        spec["device_map"],
        "--max-memory-gpu",
        spec["max_memory_gpu"],
        "--max-memory-cpu",
        spec["max_memory_cpu"],
        "--offload-folder",
        folder,
    ]
    return {
        "strategy": name,
        "serve_args": serve_args,
        "requires_offload": True,
        "offload_folder": folder,
        "max_memory_gpu": spec["max_memory_gpu"],
        "max_memory_cpu": spec["max_memory_cpu"],
    }


def _serve_profile(model: str, *, base_root: Path, serve_url: str, runtime_strategy: str = "") -> dict[str, Any]:
    profile = model_profile(model)
    root, candidates = _pick_root(model, base_root)
    aliases = list(profile.get("serve_aliases", [])) or [model_key(model)]
    alias = aliases[0]
    model_ref = str(profile.get("model_ref", model))
    endpoint_url = serve_url.rstrip("/")
    port = _endpoint_port(endpoint_url)
    runtime = _runtime_config(model, runtime_strategy)
    runtime_args = " ".join(f'"{arg}"' if " " in arg else arg for arg in runtime["serve_args"])
    runtime_suffix = f" {runtime_args}" if runtime_args else ""
    return {
        "schema": "harness.model-endpoint-profile/v1",
        "profile_id": f"serve-{model_key(model)}",
        "model": model,
        "model_key": model_key(model),
        "backend": "serve",
        "provider_role": provider_role("serve"),
        "model_ref": model_ref,
        "model_root": str(root),
        "candidate_roots": candidates,
        "root_exists": root.exists(),
        "endpoint_url": endpoint_url,
        "health_url": f"{endpoint_url}/health",
        "generate_url": f"{endpoint_url}/generate",
        "agentic_backend": "harness.local_agent.ServeBackend",
        "launch_command_template": (
            f'set "SERVE_MODEL_ALIAS={alias}" && '
            f'set "SERVE_MODEL_REF={model_ref}" && '
            f'set "SERVE_PORT={port}" && '
            f'python harness/serve.py --model-profile {alias} --model-ref "{model_ref}" --port {port}{runtime_suffix}'
        ),
        "required_env": ["SERVE_MODEL_ALIAS", "SERVE_MODEL_PATH", "SERVE_MODEL_REF", "SERVE_ADAPTER_PATH", "SERVE_PORT"],
        "env_presence": {
            name: bool(os.environ.get(name))
            for name in ["SERVE_MODEL_ALIAS", "SERVE_MODEL_PATH", "SERVE_MODEL_REF", "SERVE_ADAPTER_PATH", "SERVE_PORT"]
        },
        "aliases": aliases,
        "runtime": runtime,
        "serve_args": runtime["serve_args"],
        "content_read": False,
        "live_probed": False,
        "supports_agentic_workflow": True,
    }


def _ollama_profile(model: str, *, base_root: Path, ollama_url: str) -> dict[str, Any]:
    profile = model_profile(model)
    root, candidates = _pick_root(model, base_root)
    selectors = list(profile.get("ollama_selectors", [])) or [model_key(model)]
    return {
        "schema": "harness.model-endpoint-profile/v1",
        "profile_id": f"ollama-{model_key(model)}",
        "model": model,
        "model_key": model_key(model),
        "backend": "ollama",
        "provider_role": provider_role("ollama"),
        "model_ref": f"ollama:{selectors[0]}",
        "model_root": str(root),
        "candidate_roots": candidates,
        "root_exists": root.exists(),
        "endpoint_url": ollama_url.rstrip("/"),
        "health_url": f"{ollama_url.rstrip('/')}/api/tags",
        "generate_url": f"{ollama_url.rstrip('/')}/api/chat",
        "agentic_backend": "harness.local_agent.OllamaBackend",
        "launch_command_template": f"ollama run {selectors[0]}",
        "required_env": ["OLLAMA_HOST"],
        "env_presence": {"OLLAMA_HOST": bool(os.environ.get("OLLAMA_HOST"))},
        "selectors": selectors,
        "content_read": False,
        "live_probed": False,
        "supports_agentic_workflow": True,
    }


def build_report(
    *,
    models: list[str],
    base_root: Path,
    serve_url: str,
    serve_urls: dict[str, str] | None = None,
    runtime_strategies: dict[str, str] | None = None,
    ollama_url: str,
) -> dict[str, Any]:
    profiles: list[dict[str, Any]] = []
    serve_urls = serve_urls or {}
    runtime_strategies = runtime_strategies or {}
    for model in models:
        profiles.append(_serve_profile(
            model,
            base_root=base_root,
            serve_url=_serve_url_for_model(model, serve_url=serve_url, serve_urls=serve_urls),
            runtime_strategy=runtime_strategies.get(model_key(model), ""),
        ))
        profiles.append(_ollama_profile(model, base_root=base_root, ollama_url=ollama_url))
    return {
        "schema": "harness.model-endpoint-profiles/v1",
        "timestamp_utc": now_utc(),
        "secret_policy": "metadata-only; no endpoint probes; no model file bodies read; env values are booleans only",
        "base_root": str(base_root),
        "models_requested": models,
        "profiles": profiles,
        "summary": {
            "models": len(models),
            "profiles": len(profiles),
            "serve_profiles": sum(1 for row in profiles if row["backend"] == "serve"),
            "ollama_profiles": sum(1 for row in profiles if row["backend"] == "ollama"),
            "existing_roots": sum(1 for row in profiles if row["root_exists"]),
            "agentic_profiles": sum(1 for row in profiles if row["supports_agentic_workflow"]),
            "live_probed": False,
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Model endpoint profiles",
        "",
        f"- Schema: `{report['schema']}`",
        f"- Timestamp UTC: `{report['timestamp_utc']}`",
        f"- Secret policy: {report['secret_policy']}",
        f"- Profiles: `{summary['profiles']}`",
        f"- Existing model roots: `{summary['existing_roots']}`",
        "",
        "| Model | Backend | Provider role | Root exists | Endpoint | Agentic backend |",
        "|---|---|---|---:|---|---|",
    ]
    for row in report["profiles"]:
        lines.append(
            "| {model} | {backend} | {role} | {exists} | {endpoint} | {agentic} |".format(
                model=row["model"],
                backend=row["backend"],
                role=row["provider_role"],
                exists=str(row["root_exists"]).lower(),
                endpoint=row["endpoint_url"],
                agentic=row["agentic_backend"],
            )
        )
    return "\n".join(lines) + "\n"


def _write(path_text: str, text: str) -> str:
    if not path_text:
        return ""
    path = Path(path_text)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return str(path)


def _store_outputs(report: dict[str, Any], *, store_root: str, run_id: str, artifacts: list[tuple[str, str]]) -> list[dict[str, Any]]:
    if not store_root:
        return []
    store = FileBackedHarnessStore(Path(store_root))
    outputs = [
        store.put_receipt(
            kind="model_endpoint_profiles",
            body=report,
            run_id=run_id,
            verdict="MODEL_ENDPOINT_PROFILES_RECORDED",
        )
    ]
    for path_text, label in artifacts:
        if path_text and Path(path_text).exists():
            outputs.append(store.copy_artifact(Path(path_text), run_id=run_id, label=label))
    return outputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", default="14B,32B")
    parser.add_argument("--base-root", default="E:/local-model-run")
    parser.add_argument("--serve-url", default="",
                        help="shared serve URL; omitted uses per-model defaults 14B=8765, 32B=8767")
    parser.add_argument("--serve-url-14b", default="")
    parser.add_argument("--serve-url-32b", default="")
    parser.add_argument("--serve-runtime-14b", default="")
    parser.add_argument("--serve-runtime-32b", default="")
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--out", default="")
    parser.add_argument("--markdown-out", default="")
    parser.add_argument("--store-root", default="")
    parser.add_argument("--run-id", default="")
    args = parser.parse_args(argv)

    report = build_report(
        models=split_names(args.models),
        base_root=Path(args.base_root),
        serve_url=args.serve_url,
        serve_urls={
            "14b": args.serve_url_14b,
            "32b": args.serve_url_32b,
        },
        runtime_strategies={
            "14b": args.serve_runtime_14b,
            "32b": args.serve_runtime_32b,
        },
        ollama_url=args.ollama_url,
    )
    json_text = json.dumps(report, indent=2, sort_keys=True)
    md_text = render_markdown(report)
    json_path = _write(args.out, json_text)
    md_path = _write(args.markdown_out, md_text)
    store_outputs = _store_outputs(
        report,
        store_root=args.store_root,
        run_id=args.run_id,
        artifacts=[
            (json_path, "model-endpoint-profiles-json"),
            (md_path, "model-endpoint-profiles-markdown"),
        ],
    )
    if store_outputs:
        report = {**report, "store_outputs": store_outputs}
        json_text = json.dumps(report, indent=2, sort_keys=True)
    print(json_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
