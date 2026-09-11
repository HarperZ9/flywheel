"""Test-only, bounded diagnostics for the real ServiceDesk module CLI.

Only fixed phase/symbol labels and line numbers cross the diagnostic boundary.
Never print frames, locals, source text, paths, argv, environment or exceptions.
"""
from __future__ import annotations

import json
import runpy
import subprocess
import sys
import threading

from tests.enterprise_envs.package_helpers import ROOT

PREFIX = "SDCLI_DIAG "
TIMEOUT = 30
MODULES = frozenset({
    "__main__", "threading", "socket", "socketserver", "selectors",
    "http.server", "http.client", "urllib.request", "subprocess", "shutil",
    "pathlib", "pathlib._local", "json", "json.encoder", "json.decoder",
    "service_desk_incident_env.cli", "service_desk_incident_env.product",
    "service_desk_incident_env.v1.e2e_cases",
    "service_desk_incident_env.v1.e2e_controls",
    "service_desk_incident_env.v1.calibration_cases",
    "service_desk_incident_env.v1.http_runtime",
    "service_desk_incident_env.v1.store", "service_desk_incident_env.v1.store_actions",
    "service_desk_incident_env.v1.descriptor", "harness.enterprise_envs.http_client",
    "harness.enterprise_envs.receipts", "harness.enterprise_envs.artifact_snapshot",
    "tests.enterprise_envs.service_desk_cli_diagnostics",
})
PHASES = frozenset({
    "cli_module", "run_e2e", "malformed_json_denial_case", "_scripted_success",
    "concurrent_isolation_case", "double_action_idempotency_case",
    "reset_atomicity_case", "restart_crash_atomicity_case", "run_calibration",
    "_write_run_artifacts", "_receipt", "scan_text_artifacts_for_secrets",
    "source_basis_manifest", "prepare_artifact_root",
})
FUNCTIONS = PHASES | frozenset({
    "main", "start", "stop", "request_json", "_patch_success", "_snapshot",
    "_watchdog", "_bootstrap", "_bootstrap_inner", "run", "wait", "select",
    "serve_forever", "_handle_request_noblock", "process_request_thread",
    "finish_request", "__init__", "handle", "handle_one_request", "do_GET",
    "do_POST", "urlopen", "open", "_open", "http_open", "do_open",
    "_get_response", "getresponse", "begin", "_read_status", "readline",
    "readinto", "recv_into", "_send_output", "getaddrinfo", "sendall",
    "acquire", "_wait_for_tstate_lock", "join", "shutdown", "server_close",
    "_bad_client_submitted_log", "_bad_mutation_without_log",
    "_wrong_attachment_target", "_closed_target_incident", "_successful_patch",
    "_successful_attachment",
    "close", "reset", "_create_schema", "domain_state", "action_log", "snapshot",
    "write_json", "read_json", "read_bytes", "write_text", "_handle_agent",
    "_handle_control", "read_json_result", "patch_incident", "add_attachment",
    "record_event", "_secret_patterns", "_classify_secret_matches",
})


def _safe_stack(frame):
    rows = []
    while frame is not None and len(rows) < 24:
        module = frame.f_globals.get("__name__")
        function = frame.f_code.co_name
        known = isinstance(module, str) and module in MODULES
        rows.append({
            "module": module if known else "external",
            "function": function if known and function in FUNCTIONS else "other",
            "line": frame.f_lineno if known else 0,
        })
        frame = frame.f_back
    return rows


def _snapshot():
    main_id = threading.main_thread().ident
    frames = sys._current_frames()
    threads = [
        {"main": ident == main_id, "frames": _safe_stack(frame)}
        for ident, frame in sorted(frames.items(), key=lambda row: row[0] != main_id)[:8]
    ]
    main_stack = next((row["frames"] for row in threads if row["main"]), [])
    phase = next((row["function"] for row in main_stack
                  if row["function"] in PHASES), "cli_module")
    return {"event": "deadline_snapshot", "phase": phase, "threads": threads}


def _emit(record):
    print(PREFIX + json.dumps(record, sort_keys=True), file=sys.stderr, flush=True)


def _watchdog(stop, delay=25):
    if not stop.wait(delay):
        _emit(_snapshot())


def _valid_record(record):
    if not isinstance(record, dict) or record.get("phase") not in PHASES:
        return False
    if record.get("event") == "entry":
        return set(record) == {"event", "phase"}
    if record.get("event") != "deadline_snapshot" or set(record) != {
            "event", "phase", "threads"}:
        return False
    threads = record["threads"]
    if not isinstance(threads, list) or len(threads) > 8:
        return False
    for thread in threads:
        if not isinstance(thread, dict) or set(thread) != {"main", "frames"}:
            return False
        if type(thread["main"]) is not bool or not isinstance(thread["frames"], list):
            return False
        if len(thread["frames"]) > 24:
            return False
        for frame in thread["frames"]:
            if not isinstance(frame, dict) or set(frame) != {"module", "function", "line"}:
                return False
            if frame["module"] not in MODULES | {"external"}:
                return False
            if frame["function"] not in FUNCTIONS | {"other"}:
                return False
            if type(frame["line"]) is not int or not 0 <= frame["line"] <= 1_000_000:
                return False
    return True


def _diagnostics(stderr):
    if isinstance(stderr, bytes):
        stderr = stderr.decode("utf-8", errors="replace")
    records = []
    for line in (stderr or "")[-65536:].splitlines():
        if not line.startswith(PREFIX) or len(line) > 32768:
            continue
        try:
            record = json.loads(line[len(PREFIX):])
            if _valid_record(record):
                records.append(json.dumps(record, sort_keys=True))
        except (ValueError, TypeError, RecursionError):
            continue
    return "\n".join(records[-2:]) or "ServiceDesk CLI diagnostics unavailable"


def run_e2e(out, env):
    """Keep the original timeout and one attempt, with safe failure evidence."""
    __tracebackhide__ = True  # pytest must not render the inherited env or private argv.
    try:
        result = subprocess.run(
            [sys.executable, "-m", "tests.enterprise_envs.service_desk_cli_diagnostics",
             "e2e", "--out", str(out)],
            cwd=ROOT, env=env, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, timeout=TIMEOUT,
        )
    except subprocess.TimeoutExpired as exc:
        failure = subprocess.TimeoutExpired("ServiceDesk source CLI e2e", TIMEOUT)
        failure.add_note(_diagnostics(exc.stderr))
        raise failure from None
    return subprocess.CompletedProcess(
        "ServiceDesk source CLI e2e", result.returncode,
        result.stdout if result.returncode == 0 else "", _diagnostics(result.stderr),
    )


def main(argv=None):
    sys.argv = ["service_desk_incident_env.cli", *(sys.argv[1:] if argv is None else argv)]
    _emit({"event": "entry", "phase": "cli_module"})
    stop = threading.Event()
    watcher = threading.Thread(target=_watchdog, args=(stop,), daemon=True)
    watcher.start()
    try:
        runpy.run_module("service_desk_incident_env.cli", run_name="__main__", alter_sys=True)
    finally:
        stop.set()


if __name__ == "__main__":
    main()
