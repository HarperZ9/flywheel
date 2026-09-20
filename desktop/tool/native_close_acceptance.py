"""Native Windows close acceptance for owned gateway cleanup.

Launches an unpacked Flywheel Windows payload, waits for the app-owned bundled
engine child, closes the real native window with WM_CLOSE, and fails if that
captured owned gateway tree survives. This is an opt-in probe for local or CI
Windows payloads; it never scans for or stops unrelated gateways.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

WM_CLOSE = 0x0010
POWERSHELL = "C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"


def _run_powershell(command: str) -> str:
    result = subprocess.run(
        [POWERSHELL, "-NoProfile", "-Command", command],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        timeout=20,
    )
    if result.returncode != 0:
        raise RuntimeError("powershell failed: " + result.stderr.strip())
    return result.stdout.strip()


def _process_rows() -> list[dict[str, Any]]:
    out = _run_powershell(
        "@(Get-CimInstance Win32_Process | "
        "Select-Object ProcessId,ParentProcessId,ExecutablePath,CreationDate) "
        "| ConvertTo-Json -Compress -Depth 3"
    )
    data = json.loads(out or "[]")
    if isinstance(data, dict):
        data = [data]
    rows: list[dict[str, Any]] = []
    for row in data:
        try:
            rows.append({
                "pid": int(row.get("ProcessId")),
                "parent_pid": int(row.get("ParentProcessId") or 0),
                "executable": str(row.get("ExecutablePath") or ""),
                "creation_time": str(row.get("CreationDate") or ""),
            })
        except (TypeError, ValueError):
            continue
    return rows


def _port_listener_rows(port: int) -> list[dict[str, Any]]:
    out = _run_powershell(
        f"@(Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort {port} "
        "-State Listen -ErrorAction SilentlyContinue | "
        "Select-Object LocalAddress,LocalPort,State,OwningProcess) "
        "| ConvertTo-Json -Compress -Depth 3"
    )
    data = json.loads(out or "[]")
    if isinstance(data, dict):
        data = [data]
    rows = _process_rows()
    by_pid = {int(row["pid"]): row for row in rows}
    listeners: list[dict[str, Any]] = []
    for row in data:
        try:
            pid = int(row.get("OwningProcess") or 0)
        except (TypeError, ValueError):
            continue
        owner = by_pid.get(pid, {})
        listeners.append({
            "pid": pid,
            "local_address": str(row.get("LocalAddress") or ""),
            "local_port": int(row.get("LocalPort") or port),
            "state": str(row.get("State") or ""),
            "executable": str(owner.get("executable") or ""),
            "parent_pid": int(owner.get("parent_pid") or 0),
            "creation_time": str(owner.get("creation_time") or ""),
        })
    return listeners


def _norm(path: str | Path) -> str:
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def _children_by_parent(rows: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    children: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        children.setdefault(int(row["parent_pid"]), []).append(row)
    return children


def _descendants(rows: list[dict[str, Any]], root_pids: list[int]) -> list[dict[str, Any]]:
    children = _children_by_parent(rows)
    found: list[dict[str, Any]] = []
    stack = list(root_pids)
    while stack:
        pid = stack.pop()
        for child in children.get(pid, []):
            if child not in found:
                found.append(child)
                stack.append(int(child["pid"]))
    return found


def _owned_gateway_rows(
    rows: list[dict[str, Any]], *, app_pid: int, engine_exe: Path
) -> list[dict[str, Any]]:
    expected = _norm(engine_exe)
    return [
        row for row in rows
        if int(row["parent_pid"]) == app_pid and _norm(row["executable"]) == expected
    ]


def _same_live_rows(captured: list[dict[str, Any]], live: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_pid = {int(row["pid"]): row for row in live}
    survivors: list[dict[str, Any]] = []
    for row in captured:
        live_row = by_pid.get(int(row["pid"]))
        if live_row and live_row.get("creation_time") == row.get("creation_time"):
            survivors.append(live_row)
    return survivors


EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)


def _visible_windows_for_pid(pid: int) -> list[int]:
    user32 = ctypes.windll.user32
    hwnds: list[int] = []

    @EnumWindowsProc
    def callback(hwnd, _param):
        found_pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(found_pid))
        if int(found_pid.value) == pid and user32.IsWindowVisible(hwnd):
            hwnds.append(int(hwnd))
        return True

    user32.EnumWindows(callback, None)
    return hwnds


def _wait_for_window(pid: int, timeout_s: float) -> int | None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        hwnds = _visible_windows_for_pid(pid)
        if hwnds:
            return hwnds[0]
        time.sleep(0.2)
    return None


def _wait_for_owned_gateway(app_pid: int, engine_exe: Path, timeout_s: float) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    deadline = time.monotonic() + timeout_s
    last_rows: list[dict[str, Any]] = []
    while time.monotonic() < deadline:
        rows = _process_rows()
        last_rows = rows
        gateways = _owned_gateway_rows(rows, app_pid=app_pid, engine_exe=engine_exe)
        if gateways:
            return gateways, rows
        time.sleep(0.25)
    return [], last_rows


def _stop_pids(pids: list[int]) -> None:
    if not pids:
        return
    joined = ",".join(str(int(pid)) for pid in pids)
    _run_powershell(
        f"Stop-Process -Id {joined} -Force -ErrorAction SilentlyContinue"
    )


def run_probe(payload_root: Path, out: Path, run_root: Path, *, cleanup: bool = True) -> dict[str, Any]:
    app = payload_root / "flywheel_desktop.exe"
    engine = payload_root / "engine" / "flywheel-gateway.exe"
    run_root.mkdir(parents=True, exist_ok=True)
    receipt: dict[str, Any] = {
        "schema": "flywheel.native-close-owned-gateway/v1",
        "payload_root": str(payload_root),
        "app_exe": str(app),
        "engine_exe": str(engine),
        "close_method": "WM_CLOSE",
        "complete": False,
        "limits": [
            "unpacked payload only",
            "native close without installer or UAC",
            "owned bundled gateway child only",
            "does not prove provider, audio, device, or release publication",
        ],
    }
    if not app.is_file() or not engine.is_file():
        receipt["error"] = "payload_missing_app_or_engine"
        out.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        return receipt
    listeners = _port_listener_rows(8799)
    if listeners:
        receipt["preexisting_port_listeners"] = listeners
        receipt["error"] = "local_gateway_port_occupied_before_launch"
        out.write_text(json.dumps(receipt, indent=2, sort_keys=True), encoding="utf-8")
        return receipt

    env = os.environ.copy()
    for name in ("home", "user", "tmp"):
        (run_root / name).mkdir(parents=True, exist_ok=True)
    env.update({
        "FLYWHEEL_HOME": str(run_root / "home"),
        "USERPROFILE": str(run_root / "user"),
        "TEMP": str(run_root / "tmp"),
        "TMP": str(run_root / "tmp"),
    })
    proc = subprocess.Popen([str(app)], cwd=str(payload_root), env=env)
    receipt["app_pid"] = proc.pid
    captured: list[dict[str, Any]] = []
    survivors: list[dict[str, Any]] = []
    cleanup_pids: list[int] = []
    try:
        hwnd = _wait_for_window(proc.pid, 20)
        receipt["window_found"] = bool(hwnd)
        receipt["window_handle"] = hwnd
        gateways, before_rows = _wait_for_owned_gateway(proc.pid, engine, 30)
        receipt["owned_gateway_pids_before_close"] = [row["pid"] for row in gateways]
        if not hwnd or not gateways:
            receipt["error"] = "native_window_or_owned_gateway_not_observed"
            return receipt
        captured = gateways + _descendants(before_rows, [int(row["pid"]) for row in gateways])
        receipt["captured_owned_tree"] = [
            {"pid": row["pid"], "parent_pid": row["parent_pid"], "executable": row["executable"]}
            for row in captured
        ]
        posted = bool(ctypes.windll.user32.PostMessageW(int(hwnd), WM_CLOSE, 0, 0))
        receipt["close_posted"] = posted
        if not posted:
            receipt["error"] = "wm_close_post_failed"
            return receipt
        try:
            receipt["app_exit_code"] = proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            receipt["error"] = "app_did_not_exit_after_wm_close"
            cleanup_pids.append(proc.pid)
            return receipt
        after_rows = _process_rows()
        survivors = _same_live_rows(captured, after_rows)
        receipt["surviving_owned_tree_after_close"] = [
            {"pid": row["pid"], "parent_pid": row["parent_pid"], "executable": row["executable"]}
            for row in survivors
        ]
        receipt["complete"] = not survivors
        if survivors:
            receipt["error"] = "owned_gateway_survived_native_close"
        return receipt
    finally:
        if cleanup:
            cleanup_pids.extend(int(row["pid"]) for row in survivors)
            if proc.poll() is None:
                cleanup_pids.append(proc.pid)
            _stop_pids(sorted(set(cleanup_pids)))
            receipt["cleanup_attempted_pids"] = sorted(set(cleanup_pids))
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(receipt, indent=2, sort_keys=True), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--payload-root", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--run-root", default="")
    parser.add_argument("--no-cleanup", action="store_true")
    args = parser.parse_args(argv)
    out = Path(args.out)
    run_root = Path(args.run_root) if args.run_root else out.parent / ("run-" + uuid.uuid4().hex)
    receipt = run_probe(Path(args.payload_root), out, run_root, cleanup=not args.no_cleanup)
    print(json.dumps({"schema": receipt["schema"] + "-summary", "complete": receipt["complete"], "out": str(out)}))
    return 0 if receipt.get("complete") is True else 1


if __name__ == "__main__":
    sys.exit(main())
