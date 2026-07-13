"""Run classifier-friction/accountability benchmark across configured backends."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.agent_recovery_bench import DryEchoBackend
from harness.benchmark_receipts import store_benchmark_outputs
from harness.classifier_friction_bench import MODES, TASKS, build_report, run_case
from harness.endpoints import build_endpoints
from harness.local_agent import OllamaBackend, ServeBackend


def _split_csv(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def _env_prefix(provider: str) -> str:
    return provider.upper().replace("-", "_")


def _with_endpoint_model(provider: str, model: str):
    env_name = f"{_env_prefix(provider)}_MODEL"
    old = os.environ.get(env_name)
    if model:
        os.environ[env_name] = model
    return env_name, old


def _restore_env(env_name: str, old: str | None) -> None:
    if old is None:
        os.environ.pop(env_name, None)
    else:
        os.environ[env_name] = old


def _backend(provider: str, args) -> tuple[Any | None, str]:
    provider = provider.lower()
    if provider == "dry":
        return DryEchoBackend(name="classifier-friction-dry", model_ref="dry:classifier-friction"), ""
    if provider == "serve":
        backend = ServeBackend(base_url=args.serve_url, name="classifier-friction-serve")
        if not backend.health():
            return None, f"serve backend unhealthy at {args.serve_url}"
        return backend, ""
    if provider == "ollama":
        backend = OllamaBackend(
            base_url=args.ollama_url,
            model=args.local_model,
            name="classifier-friction-ollama",
        )
        if not backend.health():
            return None, f"ollama backend unhealthy at {args.ollama_url}"
        if getattr(backend, "_resolved", ""):
            backend.name = f"classifier-friction-ollama:{backend._resolved}"
        return backend, ""
    if not args.allow_online:
        return None, f"online provider {provider} skipped; pass --allow-online"
    endpoint_provider = "opencode" if provider == "open-code" else provider
    env_name, old = _with_endpoint_model(endpoint_provider, args.endpoint_model)
    try:
        backends = build_endpoints(providers=[endpoint_provider], modes=tuple(_split_csv(args.modes)))
    finally:
        _restore_env(env_name, old)
    if not backends:
        return None, f"no configured endpoint backend for provider={provider}"
    return backends[0], ""


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Classifier Friction Benchmark",
        "",
        report["provider_native_safety_note"],
        "",
        f"- timestamp_utc: {report['timestamp_utc']}",
        f"- providers: {', '.join(report['providers'])}",
        f"- modes: {', '.join(report['modes'])}",
        f"- tasks: {', '.join(report['tasks'])}",
        "",
        "| Provider | Mode | Cases | Pass rate | Quality | Task focus | Accountability | Proof surface | Byte witness | Workspace limit | Refusal | Unnecessary refusal | Provider guardrail observed | Error | Mean latency ms |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in report["summary"]["rows"]:
        lines.append(
            "| "
            f"{row['provider']} | "
            f"{row['mode']} | "
            f"{row['cases']} | "
            f"{row['pass_rate']} | "
            f"{row['mean_quality_score']} | "
            f"{row['mean_task_focus_score']} | "
            f"{row['mean_accountability_score']} | "
            f"{row['mean_proof_surface_score']} | "
            f"{row['mean_byte_witness_score']} | "
            f"{row['mean_workspace_limit_score']} | "
            f"{row['refusal_rate']} | "
            f"{row['unnecessary_refusal_rate']} | "
            f"{row['provider_native_guardrail_observed_rate']} | "
            f"{row['error_rate']} | "
            f"{row['mean_latency_ms']} |"
        )
    lines.extend(["", "## Deltas", ""])
    for delta in report["deltas"]:
        lines.append(f"- `{delta['provider']}` `{delta['comparison']}`: {delta}")
    lines.append("")
    if report.get("skipped"):
        lines.extend(["## Skipped", ""])
        for item in report["skipped"]:
            lines.append(f"- `{item['provider']}`: {item['reason']}")
        lines.append("")
    return "\n".join(lines)


def _write(path: Path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return str(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--providers", default="dry,serve,codex")
    parser.add_argument("--modes-to-test", default="guardrail_on,guardrail_off,accountability_first")
    parser.add_argument("--allow-online", action="store_true")
    parser.add_argument("--endpoint-model", default="gpt-5.3-codex-spark")
    parser.add_argument("--modes", default="plan")
    parser.add_argument("--serve-url", default="http://127.0.0.1:8765")
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--local-model", default="qwen2.5:7b")
    parser.add_argument("--task-id", default="", help="Comma-separated task ids to run; defaults to --max-tasks slice.")
    parser.add_argument("--max-tasks", type=int, default=1)
    parser.add_argument("--timeout-seconds", type=int, default=120)
    parser.add_argument("--max-tokens", type=int, default=500)
    parser.add_argument("--out-root", default="C:/tmp/classifier_friction_benchmark")
    parser.add_argument("--out", default="")
    parser.add_argument("--markdown-out", default="")
    parser.add_argument("--store-root", default="")
    parser.add_argument("--run-id", default="")
    args = parser.parse_args(argv)

    providers = _split_csv(args.providers)
    modes = [mode for mode in _split_csv(args.modes_to_test) if mode in MODES]
    if not modes:
        raise ValueError(f"no valid modes selected; valid modes: {', '.join(MODES)}")
    selected_task_ids = _split_csv(args.task_id)
    if selected_task_ids:
        tasks_by_id = {task.task_id: task for task in TASKS}
        missing = [task_id for task_id in selected_task_ids if task_id not in tasks_by_id]
        if missing:
            raise ValueError(
                f"unknown task id(s): {', '.join(missing)}; valid tasks: "
                f"{', '.join(task.task_id for task in TASKS)}"
            )
        tasks = [tasks_by_id[task_id] for task_id in selected_task_ids]
    else:
        tasks = list(TASKS[:args.max_tasks]) if args.max_tasks > 0 else list(TASKS)
    results: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    for provider in providers:
        backend, reason = _backend(provider, args)
        if backend is None:
            skipped.append({"provider": provider, "reason": reason})
            continue
        for task_index, task in enumerate(tasks):
            for mode_index, mode in enumerate(modes):
                results.append(run_case(
                    task,
                    backend,
                    provider=provider,
                    mode=mode,
                    seed=(task_index * 100) + mode_index,
                    timeout_seconds=args.timeout_seconds,
                    max_tokens=args.max_tokens,
                ))

    report = build_report(
        provider_order=providers,
        mode_order=modes,
        results=results,
        task_order=[task.task_id for task in tasks],
    )
    report["timestamp_utc"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    report["skipped"] = skipped
    report["config"] = {
        "endpoint_model": args.endpoint_model,
        "provider_modes": args.modes,
        "serve_url": args.serve_url,
        "ollama_url": args.ollama_url,
        "local_model": args.local_model,
        "task_id": args.task_id,
        "selected_task_ids": [task.task_id for task in tasks],
        "max_tasks": args.max_tasks,
        "timeout_seconds": args.timeout_seconds,
        "max_tokens": args.max_tokens,
    }

    run_root = Path(args.out_root).resolve() / datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    out_json = Path(args.out).resolve() if args.out else run_root / "classifier_friction_benchmark.json"
    out_md = Path(args.markdown_out).resolve() if args.markdown_out else run_root / "classifier_friction_benchmark.md"
    report["artifacts"] = {
        "json": str(out_json),
        "markdown": str(out_md),
    }
    json_path = _write(out_json, json.dumps(report, indent=2, sort_keys=True))
    md_path = _write(out_md, render_markdown(report))
    store_outputs = store_benchmark_outputs(
        report,
        store_root=args.store_root,
        kind="classifier_friction_benchmark",
        run_id=args.run_id,
        artifact_paths=[
            (json_path, "classifier-friction-benchmark-json"),
            (md_path, "classifier-friction-benchmark-markdown"),
        ],
    )
    if store_outputs:
        report = {**report, "store_outputs": store_outputs}
        _write(out_json, json.dumps(report, indent=2, sort_keys=True))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
