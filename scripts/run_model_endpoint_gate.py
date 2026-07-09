"""Run bounded live gates against local model endpoint profiles."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.benchmark_receipts import store_benchmark_outputs  # noqa: E402
from harness.local_agent import BackendError, OllamaBackend, ServeBackend  # noqa: E402


DEFAULT_PROMPT = "Reply with a short sentence confirming the local endpoint gate is active."


def now_utc() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _split_csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def _load_profiles(path_text: str) -> list[dict[str, Any]]:
    if not path_text:
        return []
    data = json.loads(Path(path_text).read_text(encoding="utf-8"))
    if data.get("schema") == "harness.model-endpoint-profile/v1":
        return [data]
    rows = data.get("profiles") if isinstance(data.get("profiles"), list) else []
    return [row for row in rows if isinstance(row, dict)]


def _backend_for_profile(profile: dict[str, Any], *, timeout_seconds: float, transport=None):
    backend = str(profile.get("backend", "")).lower()
    endpoint = str(profile.get("endpoint_url", "")).rstrip("/")
    if backend == "serve":
        kwargs = {"base_url": endpoint, "name": "serve", "timeout": timeout_seconds}
        if transport is not None:
            kwargs["transport"] = transport
        return ServeBackend(**kwargs)
    if backend == "ollama":
        selectors = profile.get("selectors") if isinstance(profile.get("selectors"), list) else []
        model = str(selectors[0]) if selectors else ""
        kwargs = {"base_url": endpoint, "model": model, "name": "ollama", "timeout": timeout_seconds}
        if transport is not None:
            kwargs["transport"] = transport
        return OllamaBackend(**kwargs)
    return None


def _stable_row_receipt(row: dict[str, Any]) -> str:
    body = {
        key: value
        for key, value in row.items()
        if key not in {"receipt_hash", "latency_ms"}
    }
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode("utf-8")).hexdigest()


def _finalize_row(row: dict[str, Any]) -> dict[str, Any]:
    row["quality_score"] = 1.0 if row.get("health_ok") and row.get("generation_ok") else 0.0
    row["receipt_hash"] = _stable_row_receipt(row)
    return row


def probe_profile(
    profile: dict[str, Any],
    *,
    prompt: str,
    timeout_seconds: float,
    max_tokens: int,
    seed: int,
    transport=None,
) -> dict[str, Any]:
    started = time.perf_counter()
    row = {
        "schema": "harness.model-endpoint-gate.row/v1",
        "profile_id": profile.get("profile_id", ""),
        "model": profile.get("model", ""),
        "model_key": profile.get("model_key", ""),
        "backend": profile.get("backend", ""),
        "provider_role": profile.get("provider_role", ""),
        "endpoint_url": profile.get("endpoint_url", ""),
        "health_ok": False,
        "generation_attempted": False,
        "generation_ok": False,
        "failure_class": "",
        "latency_ms": 0,
        "quality_score": 0.0,
        "receipt_hash": "",
        "response_sha256": "",
        "response_chars": 0,
        "model_ref": "",
    }
    backend = _backend_for_profile(profile, timeout_seconds=timeout_seconds, transport=transport)
    if backend is None:
        row["failure_class"] = "unsupported_backend"
        row["latency_ms"] = round((time.perf_counter() - started) * 1000, 3)
        return _finalize_row(row)
    try:
        row["health_ok"] = bool(backend.health())
        if not row["health_ok"]:
            row["failure_class"] = "endpoint_unavailable"
            row["latency_ms"] = round((time.perf_counter() - started) * 1000, 3)
            return _finalize_row(row)
        row["generation_attempted"] = True
        result = backend.chat(
            [{"role": "user", "content": prompt}],
            system="You are running a bounded local endpoint gate.",
            max_tokens=max_tokens,
            temperature=0.0,
            seed=seed,
        )
        text = str(result.get("text", ""))
        row["generation_ok"] = bool(text.strip())
        row["failure_class"] = "" if row["generation_ok"] else "empty_generation"
        row["response_sha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest() if text else ""
        row["response_chars"] = len(text)
        row["model_ref"] = str(result.get("model_ref", ""))
    except BackendError as exc:
        row["failure_class"] = "endpoint_error"
        row["error_type"] = type(exc).__name__
    finally:
        row["latency_ms"] = round((time.perf_counter() - started) * 1000, 3)
    return _finalize_row(row)


def build_report(
    *,
    profile_artifact: str,
    models: list[str],
    backends: list[str],
    prompt: str = DEFAULT_PROMPT,
    timeout_seconds: float = 30.0,
    max_tokens: int = 64,
    seed: int = 0,
    transport=None,
) -> dict[str, Any]:
    profiles = _load_profiles(profile_artifact)
    wanted_models = {item.lower() for item in models}
    wanted_backends = {item.lower() for item in backends}
    selected = [
        profile
        for profile in profiles
        if (not wanted_models or str(profile.get("model", "")).lower() in wanted_models)
        and (not wanted_backends or str(profile.get("backend", "")).lower() in wanted_backends)
    ]
    rows = [
        probe_profile(
            profile,
            prompt=prompt,
            timeout_seconds=timeout_seconds,
            max_tokens=max_tokens,
            seed=seed,
            transport=transport,
        )
        for profile in selected
    ]
    return {
        "schema": "harness.model-endpoint-gate/v1",
        "timestamp_utc": now_utc(),
        "profile_artifact": profile_artifact,
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "rows": rows,
        "summary": {
            "profiles_loaded": len(profiles),
            "profiles_selected": len(selected),
            "health_ok_rows": sum(1 for row in rows if row.get("health_ok")),
            "generation_ok_rows": sum(1 for row in rows if row.get("generation_ok")),
            "failed_rows": sum(1 for row in rows if row.get("failure_class")),
            "models_observed": sorted({str(row.get("model", "")) for row in rows if row.get("model")}),
            "backends_observed": sorted({str(row.get("backend", "")) for row in rows if row.get("backend")}),
            "provider_roles_observed": sorted({str(row.get("provider_role", "")) for row in rows if row.get("provider_role")}),
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Model endpoint gate",
        "",
        f"- Schema: `{report['schema']}`",
        f"- Profiles selected: `{summary['profiles_selected']}` / `{summary['profiles_loaded']}`",
        f"- Health OK rows: `{summary['health_ok_rows']}`",
        f"- Generation OK rows: `{summary['generation_ok_rows']}`",
        f"- Failed rows: `{summary['failed_rows']}`",
        "",
        "| Model | Backend | Role | Health | Generation | Failure | Latency ms |",
        "|---|---|---|---:|---:|---|---:|",
    ]
    for row in report["rows"]:
        lines.append(
            "| {model} | {backend} | {role} | {health} | {generation} | {failure} | {latency} |".format(
                model=row.get("model", ""),
                backend=row.get("backend", ""),
                role=row.get("provider_role", ""),
                health=str(row.get("health_ok", False)).lower(),
                generation=str(row.get("generation_ok", False)).lower(),
                failure=row.get("failure_class", ""),
                latency=row.get("latency_ms", 0),
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile-artifact", required=True)
    parser.add_argument("--models", default="")
    parser.add_argument("--backends", default="")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument("--max-tokens", type=int, default=64)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", default="")
    parser.add_argument("--markdown-out", default="")
    parser.add_argument("--store-root", default="")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--strict-exit", action="store_true")
    args = parser.parse_args(argv)

    report = build_report(
        profile_artifact=args.profile_artifact,
        models=_split_csv(args.models),
        backends=_split_csv(args.backends),
        prompt=args.prompt,
        timeout_seconds=args.timeout_seconds,
        max_tokens=args.max_tokens,
        seed=args.seed,
    )
    json_text = json.dumps(report, indent=2, sort_keys=True)
    md_text = render_markdown(report)
    json_path = _write(args.out, json_text)
    md_path = _write(args.markdown_out, md_text)
    store_outputs = store_benchmark_outputs(
        report,
        store_root=args.store_root,
        kind="model_endpoint_gate",
        run_id=args.run_id,
        verdict="MODEL_ENDPOINT_GATE_PASS" if report["summary"]["failed_rows"] == 0 else "MODEL_ENDPOINT_GATE_PARTIAL",
        artifact_paths=[
            (json_path, "model-endpoint-gate-json"),
            (md_path, "model-endpoint-gate-markdown"),
        ],
    )
    if store_outputs:
        report = {**report, "store_outputs": store_outputs}
        json_text = json.dumps(report, indent=2, sort_keys=True)
    print(json_text)
    return 1 if args.strict_exit and report["summary"]["failed_rows"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
