"""Run deterministic stateful UnisonAI-inspired benchmark fixtures."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.benchmark_receipts import store_benchmark_outputs  # noqa: E402
from harness.endpoints import build_endpoints  # noqa: E402
from harness.local_agent import OllamaBackend, ServeBackend  # noqa: E402
from harness.unisonai_stateful_bench import (  # noqa: E402
    render_markdown,
    run_unisonai_stateful_backend_benchmark,
    run_unisonai_stateful_benchmark,
)
from harness.provider_roles import annotate_provider_roles, provider_alias_map, provider_roles_for  # noqa: E402


class ScriptedActionBackend:
    name = "scripted-unisonai-actions"

    def __init__(self, text: str):
        self.text = text

    def chat(self, messages, *, system, max_tokens, temperature, seed):
        return {"text": self.text, "model_ref": "scripted:unisonai-actions", "seed": seed}


def _split_csv(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def _sanitize(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in value)


def _default_actions(model_ref: str) -> list[dict]:
    return [
        {
            "op": "correct",
            "question": "What is 2 + 2?",
            "bad_answer": "5",
            "good_answer": "4",
            "territory": "arithmetic",
        },
        {
            "op": "correct",
            "question": "What is 3 + 3?",
            "bad_answer": "7",
            "good_answer": "6",
            "territory": "arithmetic",
        },
        {"op": "answer", "question": "What is 2 + 2?"},
        {
            "op": "self_play_probe",
            "question": "What is the capital of Atlantis?",
            "proposed_answer": "Poseidon City",
        },
        {
            "op": "scorecard",
            "items": [
                {"id": "fixed-001", "model_ref": model_ref, "answer": "4", "expected": "4"},
                {"id": "fixed-002", "model_ref": model_ref, "answer": "blue", "expected": "red"},
            ],
        },
        {
            "op": "scorecard",
            "items": [
                {"id": "fixed-001", "model_ref": model_ref, "answer": "4", "expected": "4"},
                {"id": "fixed-002", "model_ref": model_ref, "answer": "blue", "expected": "red"},
            ],
        },
        {
            "op": "discord_ingest",
            "configured_channel": "channel-allowed",
            "channel_id": "channel-allowed",
            "text": "Document received; tool trace attached.",
            "token": "bot-secret",
            "tool_trace": {"tool": "ingest", "status": "ok"},
        },
        {
            "op": "discord_ingest",
            "configured_channel": "channel-allowed",
            "channel_id": "channel-other",
            "text": "bot-secret leaked",
            "token": "bot-secret",
            "tool_trace": {"tool": "ingest", "status": "blocked"},
        },
    ]


def _skipped(provider: str, reason: str) -> dict:
    return {
        "schema": "unisonai.stateful-backend-benchmark/v1",
        "provider": provider,
        "backend_name": "",
        "model_ref": "",
        "live": False,
        "operational": False,
        "skipped": True,
        "skip_reason": reason,
        "passed": False,
        "pass_rate": 0.0,
        "failure_class": "skipped",
        "action_count": 0,
        "metrics": [],
        "receipts": {},
    }


def _build_endpoint_backends(provider: str, modes: tuple[str, ...], model: str):
    originals: dict[str, str | None] = {}
    if model:
        env_name = f"{provider.upper().replace('-', '_')}_MODEL"
        originals[env_name] = os.environ.get(env_name)
        os.environ[env_name] = model
    try:
        return build_endpoints(providers=[provider], modes=modes)
    finally:
        for env_name, original in originals.items():
            if original is None:
                os.environ.pop(env_name, None)
            else:
                os.environ[env_name] = original


def _backend_for_provider(provider: str, args):
    provider = provider.lower().strip()
    if provider == "dry":
        payload = json.dumps({"actions": _default_actions("dry:unisonai-actions")})
        return ScriptedActionBackend(payload), {"live": False, "requested_model": "dry"}
    if provider == "serve":
        backend = ServeBackend(base_url=args.serve_url, name="unisonai-stateful-serve")
        if not backend.health():
            return None, _skipped(provider, f"serve backend unhealthy at {args.serve_url}")
        return backend, {"live": True, "requested_model": args.local_model or "14b-cpt-adapter"}
    if provider == "ollama":
        backend = OllamaBackend(
            base_url=args.ollama_url,
            model=args.ollama_model,
            name="unisonai-stateful-ollama",
        )
        if not backend.health():
            return None, _skipped(provider, f"ollama backend unhealthy at {args.ollama_url}")
        if getattr(backend, "_resolved", ""):
            backend.name = f"unisonai-stateful-ollama:{backend._resolved}"
        return backend, {"live": True, "requested_model": args.ollama_model}
    endpoint_provider = "opencode" if provider == "open-code" else provider
    modes = tuple(_split_csv(args.modes)) or ("plan", "api", "provider", "cloud")
    backends = _build_endpoint_backends(endpoint_provider, modes, args.endpoint_model)
    if not backends:
        return None, _skipped(
            provider,
            f"no configured endpoint backend for provider={provider} modes={','.join(modes)}",
        )
    return backends[0], {"live": True, "requested_model": args.endpoint_model}


def _provider_matrix(args) -> dict:
    rows = []
    providers = _split_csv(args.providers)
    for provider in providers:
        backend, metadata = _backend_for_provider(provider, args)
        if backend is None:
            rows.append(metadata)
            continue
        if hasattr(backend, "timeout"):
            try:
                backend.timeout = min(float(getattr(backend, "timeout")), args.backend_timeout_seconds)
            except (TypeError, ValueError):
                backend.timeout = args.backend_timeout_seconds
        result = run_unisonai_stateful_backend_benchmark(
            backend,
            Path(args.state_root) / _sanitize(provider),
            repair_json=args.repair_json,
        )
        result.update({
            "provider": provider,
            "live": bool(metadata.get("live", False)),
            "operational": bool(result.get("action_count", 0) and result.get("receipts")),
            "skipped": False,
            "requested_model": metadata.get("requested_model", ""),
        })
        rows.append(result)
    annotate_provider_roles(rows)
    provider_roles = provider_roles_for(providers)
    active = [row for row in rows if not row.get("skipped")]
    pass_rates = [float(row.get("pass_rate", 0.0)) for row in active]
    repair_attempts = [
        row for row in active if row.get("repair", {}).get("attempted")
    ]
    repair_successes = [
        row for row in active if row.get("repair", {}).get("succeeded")
    ]
    return {
        "schema": "unisonai.stateful-provider-matrix/v1",
        "timestamp_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "providers_requested": providers,
        "provider_roles_requested": provider_roles,
        "provider_aliases": provider_alias_map(),
        "rows": rows,
        "summary": {
            "rows": len(rows),
            "provider_role_ids": provider_roles,
            "operational_rows": sum(1 for row in rows if row.get("operational")),
            "skipped_rows": sum(1 for row in rows if row.get("skipped")),
            "live_rows": sum(1 for row in rows if row.get("live")),
            "mean_pass_rate": round(mean(pass_rates), 3) if pass_rates else 0.0,
            "passed_rows": sum(1 for row in active if row.get("passed")),
            "failed_rows": sum(1 for row in active if not row.get("passed")),
            "repair_attempted_rows": len(repair_attempts),
            "repair_succeeded_rows": len(repair_successes),
            "repair_success_rate": round(len(repair_successes) / len(repair_attempts), 3)
            if repair_attempts
            else 0.0,
        },
    }


def _benchmark_kind(result: dict) -> str:
    schema = result.get("schema", "")
    if schema == "unisonai.stateful-provider-matrix/v1":
        return "unisonai_stateful_provider_matrix"
    if schema == "unisonai.stateful-backend-benchmark/v1":
        return "unisonai_stateful_backend_benchmark"
    return "unisonai_stateful_benchmark"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-root", default="C:/tmp/unisonai_stateful_bench_state")
    parser.add_argument("--out", default="C:/tmp/unisonai_stateful_benchmark.json")
    parser.add_argument("--markdown-out", default="")
    parser.add_argument("--providers", default="", help="comma-separated provider matrix")
    parser.add_argument("--serve-url", default="http://127.0.0.1:8765")
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--ollama-model", default="qwen2.5:7b")
    parser.add_argument("--local-model", default="")
    parser.add_argument("--endpoint-model", default="gpt-5.3-codex-spark")
    parser.add_argument("--modes", default="plan,api,provider,cloud")
    parser.add_argument("--backend-timeout-seconds", type=float, default=150.0)
    parser.add_argument("--repair-json", action="store_true")
    parser.add_argument(
        "--backend-actions-json",
        default="",
        help="run backend-action fixture using this JSON payload as a scripted backend response",
    )
    parser.add_argument("--store-root", default="")
    parser.add_argument("--run-id", default="")
    args = parser.parse_args(argv)

    if args.providers:
        result = _provider_matrix(args)
    elif args.backend_actions_json:
        actions_text = Path(args.backend_actions_json).read_text(encoding="utf-8")
        result = run_unisonai_stateful_backend_benchmark(
            ScriptedActionBackend(actions_text),
            Path(args.state_root),
            repair_json=args.repair_json,
        )
    else:
        result = run_unisonai_stateful_benchmark(Path(args.state_root))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    if args.markdown_out:
        md = Path(args.markdown_out)
        md.parent.mkdir(parents=True, exist_ok=True)
        md.write_text(render_markdown(result), encoding="utf-8")
    store_outputs = store_benchmark_outputs(
        result,
        store_root=args.store_root,
        kind=_benchmark_kind(result),
        run_id=args.run_id,
        artifact_paths=[
            (str(out), "unisonai-stateful-json"),
            (args.markdown_out, "unisonai-stateful-markdown"),
        ],
    )
    print(f"out_json={out}")
    if args.markdown_out:
        print(f"out_md={args.markdown_out}")
    if store_outputs:
        print(f"store_outputs={json.dumps(store_outputs, sort_keys=True)}")
    if result.get("schema") == "unisonai.stateful-provider-matrix/v1":
        print(f"operational_rows={result['summary']['operational_rows']}")
        print(f"mean_pass_rate={result['summary']['mean_pass_rate']}")
        return 0
    print(f"passed={result['passed']} pass_rate={result['pass_rate']}")
    print(f"packet_sha256={result['packet_sha256']}")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
