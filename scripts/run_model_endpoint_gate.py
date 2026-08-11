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


def _canonical_sha256(value: dict[str, Any]) -> str:
    body = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


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
        kwargs = {"base_url": endpoint, "model": str(selectors[0]) if selectors else "", "name": "ollama", "timeout": timeout_seconds}
        if transport is not None:
            kwargs["transport"] = transport
        return OllamaBackend(**kwargs)
    return None


def _ollama_identity(profile: dict[str, Any], obj: dict[str, Any]) -> tuple[str, str]:
    selectors = profile.get("selectors") if isinstance(profile.get("selectors"), list) else []
    wanted = str(selectors[0]) if selectors else ""
    models = obj.get("models") if isinstance(obj.get("models"), list) else []
    for model in models:
        if not isinstance(model, dict):
            continue
        name = str(model.get("name") or model.get("model") or "")
        if name == wanted:
            return f"ollama:{name}", str(model.get("digest", ""))
    return "", ""


def _health_probe(profile: dict[str, Any], backend: Any) -> tuple[bool, str, dict[str, Any]]:
    backend_name = str(profile.get("backend", "")).lower()
    endpoint = str(profile.get("endpoint_url", "")).rstrip("/")
    url = f"{endpoint}/health" if backend_name == "serve" else f"{endpoint}/api/tags" if backend_name == "ollama" else ""
    if not url:
        return False, "unsupported_backend", {"health_status": 0}
    try:
        status, obj = backend.transport("GET", url, None, 5.0)
    except (OSError, ConnectionError):
        return False, "endpoint_unavailable", {"health_status": 0}
    except Exception as exc:
        return False, "health_probe_error", {"health_status": 0, "error_type": type(exc).__name__}
    detail: dict[str, Any] = {"health_status": status}
    if backend_name == "serve":
        observed = str(obj.get("model_ref", "")) if isinstance(obj, dict) else ""
        detail["health_model_ref"] = observed
        if status == 200 and isinstance(obj, dict) and obj.get("ok"):
            expected = str(profile.get("model_ref", ""))
            return (True, "health_model_ref_mismatch", detail) if expected and observed and expected != observed else (True, "", detail)
    elif status == 200 and isinstance(obj, dict) and obj.get("models"):
        observed, digest = _ollama_identity(profile, obj)
        detail.update(health_model_ref=observed, ollama_digest=digest)
        return True, "", detail
    if status == 404:
        return False, "wrong_service_or_path", detail
    if status == 200:
        return False, "wrong_service_or_schema", detail
    return False, "health_http_error", detail


def _stable_row_receipt(row: dict[str, Any]) -> str:
    body = {key: value for key, value in row.items() if key not in {"receipt_hash", "latency_ms"}}
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode("utf-8")).hexdigest()


def _finalize_row(row: dict[str, Any], started: float) -> dict[str, Any]:
    row["latency_ms"] = round((time.perf_counter() - started) * 1000, 3)
    row["observed_at"] = now_utc()
    row["quality_score"] = 1.0 if row.get("health_ok") and row.get("generation_ok") else 0.0
    row["receipt_hash"] = _stable_row_receipt(row)
    return row


def probe_profile(
    profile: dict[str, Any], *, prompt: str, timeout_seconds: float, max_tokens: int,
    seed: int, run_id: str = "", transport=None,
) -> dict[str, Any]:
    started = time.perf_counter()
    row = {
        "schema": "harness.model-endpoint-gate.row/v1",
        "selected_profile_id": profile.get("profile_id", ""), "profile_id": profile.get("profile_id", ""),
        "profile_sha256": _canonical_sha256(profile), "model": profile.get("model", ""),
        "model_key": profile.get("model_key", ""), "backend": profile.get("backend", ""),
        "provider_role": profile.get("provider_role", ""), "endpoint_url": profile.get("endpoint_url", ""),
        "expected_model_ref": str(profile.get("model_ref", "")), "observed_model_ref": "", "model_ref": "",
        "health_ok": False, "health_status": 0, "health_model_ref": "", "ollama_digest": "",
        "generation_attempted": False, "generation_ok": False, "failure_class": "",
        "response_sha256": "", "response_chars": 0, "run_id": run_id,
    }
    backend = _backend_for_profile(profile, timeout_seconds=timeout_seconds, transport=transport)
    if backend is None:
        row["failure_class"] = "unsupported_backend"
        return _finalize_row(row, started)
    try:
        health_ok, health_failure, detail = _health_probe(profile, backend)
        row.update(health_ok=health_ok, health_status=detail.get("health_status", 0),
                   health_model_ref=detail.get("health_model_ref", ""), ollama_digest=detail.get("ollama_digest", ""))
        if detail.get("error_type"):
            row["error_type"] = detail["error_type"]
        if health_failure == "health_model_ref_mismatch":
            row.update(failure_class=health_failure, observed_model_ref=row["health_model_ref"], model_ref=row["health_model_ref"])
            return _finalize_row(row, started)
        if not health_ok:
            row["failure_class"] = health_failure or "endpoint_unavailable"
            return _finalize_row(row, started)
        row["generation_attempted"] = True
        result = backend.chat(
            [{"role": "user", "content": prompt}], system="You are running a bounded local endpoint gate.",
            max_tokens=max_tokens, temperature=0.0, seed=seed,
        )
        text = str(result.get("text", ""))
        observed = str(result.get("model_ref", ""))
        row.update(generation_ok=bool(text.strip()), observed_model_ref=observed, model_ref=observed,
                   response_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest() if text else "", response_chars=len(text))
        row["failure_class"] = "" if row["generation_ok"] else "empty_generation"
        if row["generation_ok"] and row["expected_model_ref"] and observed != row["expected_model_ref"]:
            row.update(generation_ok=False, failure_class="model_ref_mismatch")
    except BackendError as exc:
        row.update(failure_class="endpoint_error", error_type=type(exc).__name__)
    return _finalize_row(row, started)


def build_report(
    *, profile_artifact: str, models: list[str], backends: list[str], prompt: str = DEFAULT_PROMPT,
    timeout_seconds: float = 30.0, max_tokens: int = 64, seed: int = 0, run_id: str = "", transport=None,
) -> dict[str, Any]:
    profiles = _load_profiles(profile_artifact)
    wanted_models, wanted_backends = {item.lower() for item in models}, {item.lower() for item in backends}
    selected = [profile for profile in profiles
                if (not wanted_models or str(profile.get("model", "")).lower() in wanted_models)
                and (not wanted_backends or str(profile.get("backend", "")).lower() in wanted_backends)]
    rows = [probe_profile(profile, prompt=prompt, timeout_seconds=timeout_seconds, max_tokens=max_tokens,
                          seed=seed, run_id=run_id, transport=transport) for profile in selected]
    return {
        "schema": "harness.model-endpoint-gate/v1", "timestamp_utc": now_utc(), "run_id": run_id,
        "profile_artifact": profile_artifact, "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "rows": rows,
        "summary": {
            "profiles_loaded": len(profiles), "profiles_selected": len(selected),
            "health_ok_rows": sum(bool(row.get("health_ok")) for row in rows),
            "generation_ok_rows": sum(bool(row.get("generation_ok")) for row in rows),
            "failed_rows": sum(bool(row.get("failure_class")) for row in rows),
            "models_observed": sorted({str(row["model"]) for row in rows if row.get("model")}),
            "backends_observed": sorted({str(row["backend"]) for row in rows if row.get("backend")}),
            "provider_roles_observed": sorted({str(row["provider_role"]) for row in rows if row.get("provider_role")}),
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Model endpoint gate", "", f"- Schema: `{report['schema']}`",
        f"- Profiles selected: `{summary['profiles_selected']}` / `{summary['profiles_loaded']}`",
        f"- Health OK rows: `{summary['health_ok_rows']}`", f"- Generation OK rows: `{summary['generation_ok_rows']}`",
        f"- Failed rows: `{summary['failed_rows']}`", "",
        "| Model | Backend | Role | Health | Status | Health ref | Generation | Failure | Latency ms |",
        "|---|---|---|---:|---:|---|---:|---|---:|",
    ]
    for row in report["rows"]:
        lines.append("| {model} | {backend} | {provider_role} | {health_ok} | {health_status} | {health_model_ref} | {generation_ok} | {failure_class} | {latency_ms} |".format(**row))
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
        profile_artifact=args.profile_artifact, models=_split_csv(args.models), backends=_split_csv(args.backends),
        prompt=args.prompt, timeout_seconds=args.timeout_seconds, max_tokens=args.max_tokens, seed=args.seed, run_id=args.run_id,
    )
    json_text, md_text = json.dumps(report, indent=2, sort_keys=True), render_markdown(report)
    json_path, md_path = _write(args.out, json_text), _write(args.markdown_out, md_text)
    outputs = store_benchmark_outputs(
        report, store_root=args.store_root, kind="model_endpoint_gate", run_id=args.run_id,
        verdict="MODEL_ENDPOINT_GATE_PASS" if report["summary"]["failed_rows"] == 0 else "MODEL_ENDPOINT_GATE_PARTIAL",
        artifact_paths=[(json_path, "model-endpoint-gate-json"), (md_path, "model-endpoint-gate-markdown")],
    )
    if outputs:
        report = {**report, "store_outputs": outputs}
        json_text = json.dumps(report, indent=2, sort_keys=True)
    print(json_text)
    return 1 if args.strict_exit and report["summary"]["failed_rows"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
