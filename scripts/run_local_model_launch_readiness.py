"""Emit non-destructive launch readiness for local model endpoint profiles."""

from __future__ import annotations

import argparse
import json
import re
import socket
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.benchmark_receipts import store_benchmark_outputs  # noqa: E402


OwnerLookup = Callable[[str, int], list[dict[str, Any]]]
PortProbe = Callable[[str, int, float], bool]

SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|secret|token|password)=([^ \t]+)"),
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
]


def now_utc() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def split_csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def _load_profiles(path_text: str) -> list[dict[str, Any]]:
    if not path_text:
        return []
    data = json.loads(Path(path_text).read_text(encoding="utf-8"))
    if data.get("schema") == "harness.model-endpoint-profile/v1":
        return [data]
    rows = data.get("profiles") if isinstance(data.get("profiles"), list) else []
    return [row for row in rows if isinstance(row, dict)]


def _redact(text: str) -> str:
    value = text or ""
    for pattern in SECRET_PATTERNS:
        value = pattern.sub(lambda match: f"{match.group(1)}=<redacted>" if match.groups() else "<redacted>", value)
    return value[:500]


def _parse_endpoint(endpoint_url: str) -> tuple[str, int]:
    parsed = urlparse(endpoint_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return host, int(port)


def _socket_port_probe(host: str, port: int, timeout_seconds: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout_seconds):
            return True
    except OSError:
        return False


def _powershell_owner_lookup(host: str, port: int) -> list[dict[str, Any]]:
    del host
    command = (
        f"$items = Get-NetTCPConnection -LocalPort {port} -ErrorAction SilentlyContinue | "
        "Where-Object { $_.OwningProcess -gt 0 } | Sort-Object OwningProcess -Unique; "
        "$rows = foreach ($item in $items) { "
        "$proc = Get-CimInstance Win32_Process -Filter \"ProcessId = $($item.OwningProcess)\" -ErrorAction SilentlyContinue; "
        "[PSCustomObject]@{"
        "pid=$item.OwningProcess;"
        "process_name=$proc.Name;"
        "command_line=$proc.CommandLine"
        "} "
        "}; "
        "$rows | ConvertTo-Json -Depth 3 -Compress"
    )
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    text = completed.stdout.strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return []
    rows = parsed if isinstance(parsed, list) else [parsed]
    clean_rows = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        clean_rows.append({
            "pid": row.get("pid", 0),
            "process_name": row.get("process_name", "") or "",
            "command_line": _redact(row.get("command_line", "") or ""),
        })
    return clean_rows


def _owner_kind(owner: dict[str, Any]) -> str:
    haystack = f"{owner.get('process_name', '')} {owner.get('command_line', '')}".lower()
    normalized = haystack.replace("\\", "/")
    if "harness/serve.py" in normalized:
        return "harness_serve"
    if "http.server" in normalized:
        return "generic_http_server"
    if "ollama" in normalized:
        return "ollama"
    if haystack.strip():
        return "other_process"
    return "unknown"


def _row_readiness(
    profile: dict[str, Any],
    *,
    owner_lookup: OwnerLookup,
    port_probe: PortProbe,
) -> dict[str, Any]:
    endpoint_url = str(profile.get("endpoint_url", ""))
    host, port = _parse_endpoint(endpoint_url)
    owners = owner_lookup(host, port)
    port_listening = bool(owners) or port_probe(host, port, 1.0)
    owner = owners[0] if owners else {}
    owner_kind = _owner_kind(owner) if owner else ("unknown_listener" if port_listening else "none")
    backend = str(profile.get("backend", "")).lower()
    model_root = str(profile.get("model_root", ""))
    root_exists = bool(profile.get("root_exists")) or (bool(model_root) and Path(model_root).exists())

    if not root_exists:
        readiness = "model_root_missing"
    elif backend != "serve":
        readiness = "external_backend_not_launch_managed"
    elif not port_listening:
        readiness = "ready_to_launch"
    elif owner_kind == "harness_serve":
        readiness = "candidate_running_gate_required"
    else:
        readiness = "port_conflict_wrong_service"

    return {
        "schema": "harness.local-model-launch-readiness.row/v1",
        "profile_id": profile.get("profile_id", ""),
        "model": profile.get("model", ""),
        "model_key": profile.get("model_key", ""),
        "backend": profile.get("backend", ""),
        "provider_role": profile.get("provider_role", ""),
        "endpoint_url": endpoint_url,
        "expected_model_ref": profile.get("model_ref", ""),
        "model_root": model_root,
        "root_exists": root_exists,
        "host": host,
        "port": port,
        "port_listening": port_listening,
        "owner_kind": owner_kind,
        "owner_pid": owner.get("pid", 0) if owner else 0,
        "owner_process": owner.get("process_name", "") if owner else "",
        "owner_command_line": owner.get("command_line", "") if owner else "",
        "readiness": readiness,
        "can_launch_without_displacing": readiness == "ready_to_launch",
        "launch_command_template": profile.get("launch_command_template", ""),
    }


def build_report(
    *,
    profile_artifact: str,
    models: list[str],
    backends: list[str],
    owner_lookup: OwnerLookup = _powershell_owner_lookup,
    port_probe: PortProbe = _socket_port_probe,
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
        _row_readiness(profile, owner_lookup=owner_lookup, port_probe=port_probe)
        for profile in selected
    ]
    blocking = {"model_root_missing", "port_conflict_wrong_service"}
    return {
        "schema": "harness.local-model-launch-readiness/v1",
        "timestamp_utc": now_utc(),
        "profile_artifact": profile_artifact,
        "secret_policy": "process command lines are redacted and truncated; no env values or model file bodies are read",
        "rows": rows,
        "summary": {
            "profiles_loaded": len(profiles),
            "profiles_selected": len(selected),
            "ready_to_launch_rows": sum(1 for row in rows if row["readiness"] == "ready_to_launch"),
            "candidate_running_rows": sum(1 for row in rows if row["readiness"] == "candidate_running_gate_required"),
            "blocking_rows": sum(1 for row in rows if row["readiness"] in blocking),
            "port_conflict_rows": sum(1 for row in rows if row["readiness"] == "port_conflict_wrong_service"),
            "models_observed": sorted({str(row.get("model", "")) for row in rows if row.get("model")}),
            "ports_observed": sorted({int(row.get("port", 0)) for row in rows if row.get("port")}),
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Local model launch readiness",
        "",
        f"- Schema: `{report['schema']}`",
        f"- Profiles selected: `{summary['profiles_selected']}` / `{summary['profiles_loaded']}`",
        f"- Ready to launch: `{summary['ready_to_launch_rows']}`",
        f"- Candidate running: `{summary['candidate_running_rows']}`",
        f"- Port conflicts: `{summary['port_conflict_rows']}`",
        f"- Blocking rows: `{summary['blocking_rows']}`",
        "",
        "| Model | Backend | Endpoint | Root | Listening | Owner kind | Readiness |",
        "|---|---|---|---:|---:|---|---|",
    ]
    for row in report["rows"]:
        lines.append(
            "| {model} | {backend} | {endpoint} | {root} | {listening} | {owner} | {readiness} |".format(
                model=row.get("model", ""),
                backend=row.get("backend", ""),
                endpoint=row.get("endpoint_url", ""),
                root=str(row.get("root_exists", False)).lower(),
                listening=str(row.get("port_listening", False)).lower(),
                owner=row.get("owner_kind", ""),
                readiness=row.get("readiness", ""),
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
    parser.add_argument("--backends", default="serve")
    parser.add_argument("--out", default="")
    parser.add_argument("--markdown-out", default="")
    parser.add_argument("--store-root", default="")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--strict-exit", action="store_true")
    args = parser.parse_args(argv)

    report = build_report(
        profile_artifact=args.profile_artifact,
        models=split_csv(args.models),
        backends=split_csv(args.backends),
    )
    json_text = json.dumps(report, indent=2, sort_keys=True)
    md_text = render_markdown(report)
    json_path = _write(args.out, json_text)
    md_path = _write(args.markdown_out, md_text)
    store_outputs = store_benchmark_outputs(
        report,
        store_root=args.store_root,
        kind="local_model_launch_readiness",
        run_id=args.run_id,
        verdict="LOCAL_MODEL_LAUNCH_READY" if report["summary"]["blocking_rows"] == 0 else "LOCAL_MODEL_LAUNCH_BLOCKED",
        artifact_paths=[
            (json_path, "local-model-launch-readiness-json"),
            (md_path, "local-model-launch-readiness-markdown"),
        ],
    )
    if store_outputs:
        report = {**report, "store_outputs": store_outputs}
        json_text = json.dumps(report, indent=2, sort_keys=True)
    print(json_text)
    return 1 if args.strict_exit and report["summary"]["blocking_rows"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
