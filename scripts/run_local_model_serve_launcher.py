"""Plan or start local harness/serve.py processes from endpoint profiles."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.benchmark_receipts import store_benchmark_outputs  # noqa: E402

LOCAL_MODEL_VENV_PYTHON = Path("E:/local-model-run/venv/Scripts/python.exe")


def default_serve_python() -> str:
    explicit = os.environ.get("LOCAL_SERVE_PYTHON", "").strip()
    if explicit:
        return explicit
    if LOCAL_MODEL_VENV_PYTHON.exists():
        return str(LOCAL_MODEL_VENV_PYTHON)
    return sys.executable


def now_utc() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def split_csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _load_profiles(path_text: str) -> list[dict[str, Any]]:
    data = json.loads(Path(path_text).read_text(encoding="utf-8"))
    if data.get("schema") == "harness.model-endpoint-profile/v1":
        return [data]
    rows = data.get("profiles") if isinstance(data.get("profiles"), list) else []
    return [row for row in rows if isinstance(row, dict)]


def _endpoint_port(endpoint_url: str) -> int:
    parsed = urlparse(endpoint_url)
    return int(parsed.port or (443 if parsed.scheme == "https" else 80))


def _profile_alias(profile: dict[str, Any]) -> str:
    aliases = profile.get("aliases") if isinstance(profile.get("aliases"), list) else []
    return str(aliases[0]) if aliases else str(profile.get("model_key", "")).lower()


def _command_for_profile(profile: dict[str, Any], *, serve_python: str) -> list[str]:
    port = _endpoint_port(str(profile.get("endpoint_url", "")))
    command = [
        serve_python,
        str(_repo_root() / "harness" / "serve.py"),
        "--model-profile",
        _profile_alias(profile),
        "--model-ref",
        str(profile.get("model_ref", "")),
        "--port",
        str(port),
    ]
    serve_args = profile.get("serve_args") if isinstance(profile.get("serve_args"), list) else []
    command.extend(str(arg) for arg in serve_args)
    return command


def _health_url(profile: dict[str, Any]) -> str:
    endpoint = str(profile.get("endpoint_url", "")).rstrip("/")
    return f"{endpoint}/health"


def _poll_health(profile: dict[str, Any], *, wait_seconds: float) -> tuple[bool, str]:
    deadline = time.time() + max(0.0, wait_seconds)
    url = _health_url(profile)
    last_error = ""
    while time.time() <= deadline:
        try:
            with urlopen(url, timeout=2.0) as response:
                body = response.read()
            parsed = json.loads(body.decode("utf-8")) if body else {}
            if parsed.get("ok"):
                return True, str(parsed.get("model_ref", ""))
            last_error = "health_schema_missing_ok"
        except Exception as exc:  # noqa: BLE001 - receipt should capture any startup failure shape
            last_error = type(exc).__name__
        time.sleep(1.0)
    return False, last_error


def _start_process(command: list[str], *, log_path: Path) -> subprocess.Popen:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = log_path.open("ab")
    process = subprocess.Popen(
        command,
        cwd=str(_repo_root()),
        stdout=log,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    log.close()
    return process


def _terminate_process(process: subprocess.Popen, *, timeout_seconds: float = 10.0) -> str:
    if process.poll() is not None:
        return f"already_exited:{process.returncode}"
    process.terminate()
    try:
        process.wait(timeout=timeout_seconds)
        return f"terminated:{process.returncode}"
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=timeout_seconds)
        return f"killed:{process.returncode}"


def _tail_log(path: Path, *, max_chars: int = 6000) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    return text[-max_chars:]


def _classify_start_failure(fallback: str, log_path: Path) -> str:
    log = _tail_log(log_path)
    lower_log = log.lower()
    if "ModuleNotFoundError: No module named 'torch'" in log:
        return "missing_dependency_torch"
    if "ModuleNotFoundError: No module named 'transformers'" in log:
        return "missing_dependency_transformers"
    if "No module named 'bitsandbytes'" in log:
        return "missing_dependency_bitsandbytes"
    if "CUDA out of memory" in log or "OutOfMemoryError" in log:
        return "cuda_out_of_memory"
    if "ValueError:" in log and "offload" in lower_log:
        return "offload_configuration_error"
    if (
        "Loading weights:" in log
        and fallback in {"URLError", "health_timeout"}
        and "traceback" not in lower_log
        and "error" not in lower_log
        and "exception" not in lower_log
    ):
        return "startup_timeout_loading_weights"
    return fallback


def _select_profiles(profiles: list[dict[str, Any]], *, models: list[str]) -> list[dict[str, Any]]:
    wanted = {item.lower() for item in models}
    return [
        profile
        for profile in profiles
        if str(profile.get("backend", "")).lower() == "serve"
        and (not wanted or str(profile.get("model", "")).lower() in wanted)
    ]


def build_report(
    *,
    profile_artifact: str,
    models: list[str],
    serve_python: str,
    start: bool = False,
    wait_seconds: float = 0.0,
    log_dir: str = "C:/tmp/local_model_serve_logs",
    terminate_on_timeout: bool = False,
) -> dict[str, Any]:
    profiles = _load_profiles(profile_artifact)
    selected = _select_profiles(profiles, models=models)
    rows: list[dict[str, Any]] = []
    for profile in selected:
        command = _command_for_profile(profile, serve_python=serve_python)
        log_path = Path(log_dir) / f"{profile.get('profile_id', 'serve')}-{int(time.time())}.log"
        row = {
            "schema": "harness.local-model-serve-launch.row/v1",
            "profile_id": profile.get("profile_id", ""),
            "model": profile.get("model", ""),
            "model_key": profile.get("model_key", ""),
            "endpoint_url": profile.get("endpoint_url", ""),
            "expected_model_ref": profile.get("model_ref", ""),
            "model_root": profile.get("model_root", ""),
            "root_exists": bool(profile.get("root_exists")),
            "serve_python": serve_python,
            "command": command,
            "log_path": str(log_path),
            "start_requested": start,
            "pid": 0,
            "health_ok": False,
            "health_model_ref": "",
            "failure_class": "",
            "terminate_on_timeout": terminate_on_timeout,
            "terminated_on_timeout": False,
            "termination_status": "",
            "process_exit_code": None,
        }
        if not row["root_exists"]:
            row["failure_class"] = "model_root_missing"
        elif start:
            process = _start_process(command, log_path=log_path)
            row["pid"] = int(process.pid)
            health_ok, health_detail = _poll_health(profile, wait_seconds=wait_seconds)
            row["health_ok"] = health_ok
            if health_ok:
                row["health_model_ref"] = health_detail
            else:
                row["failure_class"] = health_detail or "health_timeout"
                if terminate_on_timeout:
                    row["termination_status"] = _terminate_process(process)
                    row["terminated_on_timeout"] = row["termination_status"].startswith(("terminated:", "killed:"))
                row["process_exit_code"] = process.poll()
                row["failure_class"] = _classify_start_failure(row["failure_class"], log_path)
        rows.append(row)
    return {
        "schema": "harness.local-model-serve-launch/v1",
        "timestamp_utc": now_utc(),
        "profile_artifact": profile_artifact,
        "start_requested": start,
        "secret_policy": "launch command contains model refs and local paths only; no env values are recorded",
        "rows": rows,
        "summary": {
            "profiles_loaded": len(profiles),
            "profiles_selected": len(selected),
            "planned_rows": sum(1 for row in rows if not row["start_requested"]),
            "started_rows": sum(1 for row in rows if row["pid"]),
            "health_ok_rows": sum(1 for row in rows if row["health_ok"]),
            "failed_rows": sum(1 for row in rows if row["failure_class"]),
            "models_observed": sorted({str(row.get("model", "")) for row in rows if row.get("model")}),
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Local model serve launcher",
        "",
        f"- Schema: `{report['schema']}`",
        f"- Start requested: `{str(report['start_requested']).lower()}`",
        f"- Profiles selected: `{summary['profiles_selected']}` / `{summary['profiles_loaded']}`",
        f"- Started rows: `{summary['started_rows']}`",
        f"- Health OK rows: `{summary['health_ok_rows']}`",
        f"- Failed rows: `{summary['failed_rows']}`",
        "",
        "| Model | Endpoint | Start | PID | Health | Failure | Log |",
        "|---|---|---:|---:|---:|---|---|",
    ]
    for row in report["rows"]:
        lines.append(
            "| {model} | {endpoint} | {start} | {pid} | {health} | {failure} | {log} |".format(
                model=row.get("model", ""),
                endpoint=row.get("endpoint_url", ""),
                start=str(row.get("start_requested", False)).lower(),
                pid=row.get("pid", 0),
                health=str(row.get("health_ok", False)).lower(),
                failure=row.get("failure_class", ""),
                log=row.get("log_path", ""),
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
    parser.add_argument("--serve-python", default=default_serve_python())
    parser.add_argument("--start", action="store_true")
    parser.add_argument("--wait-seconds", type=float, default=0.0)
    parser.add_argument("--log-dir", default="C:/tmp/local_model_serve_logs")
    parser.add_argument("--terminate-on-timeout", action="store_true")
    parser.add_argument("--out", default="")
    parser.add_argument("--markdown-out", default="")
    parser.add_argument("--store-root", default="")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--strict-exit", action="store_true")
    args = parser.parse_args(argv)

    report = build_report(
        profile_artifact=args.profile_artifact,
        models=split_csv(args.models),
        serve_python=args.serve_python,
        start=args.start,
        wait_seconds=args.wait_seconds,
        log_dir=args.log_dir,
        terminate_on_timeout=args.terminate_on_timeout,
    )
    json_text = json.dumps(report, indent=2, sort_keys=True)
    md_text = render_markdown(report)
    json_path = _write(args.out, json_text)
    md_path = _write(args.markdown_out, md_text)
    verdict = "LOCAL_MODEL_SERVE_HEALTHY" if report["summary"]["health_ok_rows"] else "LOCAL_MODEL_SERVE_PLANNED"
    if args.start and report["summary"]["failed_rows"]:
        verdict = "LOCAL_MODEL_SERVE_PARTIAL"
    store_outputs = store_benchmark_outputs(
        report,
        store_root=args.store_root,
        kind="local_model_serve_launch",
        run_id=args.run_id,
        verdict=verdict,
        artifact_paths=[
            (json_path, "local-model-serve-launch-json"),
            (md_path, "local-model-serve-launch-markdown"),
        ],
    )
    if store_outputs:
        report = {**report, "store_outputs": store_outputs}
        json_text = json.dumps(report, indent=2, sort_keys=True)
    print(json_text)
    return 1 if args.strict_exit and report["summary"]["failed_rows"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
