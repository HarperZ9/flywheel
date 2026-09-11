"""Platform adapters for installed-launch acceptance."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from urllib import error, request

try:
    from .installed_launch_acceptance_shortcuts import resolve_links
    from .installed_launch_acceptance_jobs import start_windows_job_process
    from .installed_launch_acceptance_model import (
        MetadataResult, NullHttpClient, NullProcessController,
        NullWindowsMetadata, ProcessHandle, ShortcutRecord, WINDOW_FLAGS,
        registry_values,
    )
except ImportError:
    from installed_launch_acceptance_shortcuts import resolve_links  # type: ignore
    from installed_launch_acceptance_jobs import start_windows_job_process  # type: ignore
    from installed_launch_acceptance_model import (  # type: ignore
        MetadataResult, NullHttpClient, NullProcessController,
        NullWindowsMetadata, ProcessHandle, ShortcutRecord, WINDOW_FLAGS,
        registry_values,
    )
import subprocess


class LocalWindowsMetadata(NullWindowsMetadata):
    def start_menu_shortcuts(self) -> list[ShortcutRecord]:
        bases = [os.environ.get("APPDATA", ""), os.environ.get("ProgramData", "")]
        name = "Microsoft/Windows/Start Menu/Programs/Flywheel/Flywheel.lnk"
        return self._resolve_links([Path(b) / name for b in bases if b])

    def desktop_shortcut(self) -> ShortcutRecord | None:
        bases = [os.environ.get("USERPROFILE", ""), os.environ.get("PUBLIC", "")]
        links = self._resolve_links([Path(b) / "Desktop/Flywheel.lnk" for b in bases if b])
        return links[0] if links else None

    def uninstall_registry(self, app_id: str, install_root: Path | None = None) -> MetadataResult:
        if os.name != "nt":
            return MetadataResult("UNTESTED", reason="not_windows")
        import winreg
        paths = [r"Software\Microsoft\Windows\CurrentVersion\Uninstall",
                 r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"]
        roots = ((winreg.HKEY_CURRENT_USER, "HKCU"), (winreg.HKEY_LOCAL_MACHINE, "HKLM"))
        entries = []
        try:
            for root, label in roots:
                for base in paths:
                    entries.extend(self._scan_uninstall_key(winreg, root, label, base))
        except PermissionError:
            return MetadataResult("ACCESS_DENIED", {"app_id": app_id})
        return self.classify_uninstall_entries(app_id, entries, install_root)

    def protocol_registration(self, scheme: str) -> MetadataResult:
        if os.name != "nt":
            return MetadataResult("UNSUPPORTED", reason="not_windows")
        import winreg
        for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_CLASSES_ROOT):
            try:
                with winreg.OpenKey(root, scheme) as key:
                    return MetadataResult("PASS", registry_values(winreg, key))
            except PermissionError:
                return MetadataResult("ACCESS_DENIED", {"scheme": scheme})
            except OSError:
                continue
        return MetadataResult("UNSUPPORTED", {"scheme": scheme})

    def classify_uninstall_entries(self, app_id: str, entries: list[dict],
                                   install_root: Path | None = None) -> MetadataResult:
        candidates = [e for e in entries if _is_flywheel_or_appid_entry(app_id, e)]
        exact = [e for e in candidates if _entry_matches_appid(app_id, e)]
        observed = {"app_id": app_id, "candidate_count": len(candidates),
                    "exact_appid_count": len(exact), "entries": candidates}
        if not candidates:
            return MetadataResult("UNSUPPORTED", {"app_id": app_id}, "not_found")
        if len(candidates) != 1 or len(exact) != 1:
            reason = "duplicate_or_ambiguous_appid" if exact else "appid_mismatch"
            return MetadataResult("FAIL", observed, reason)
        if install_root and not _entry_matches_install_root(install_root, exact[0]):
            observed["install_root_expected"] = str(install_root)
            return MetadataResult("FAIL", observed, "install_root_mismatch")
        exact[0]["candidate_count"] = 1
        exact[0]["exact_appid_count"] = 1
        return MetadataResult("PASS", exact[0])

    def _scan_uninstall_key(self, winreg, root, root_name: str, base: str) -> list[dict]:
        entries = []
        try:
            with winreg.OpenKey(root, base) as key:
                for index in range(winreg.QueryInfoKey(key)[0]):
                    name = winreg.EnumKey(key, index)
                    with winreg.OpenKey(key, name) as sub:
                        values = registry_values(winreg, sub)
                    values["registry_key"] = name
                    values["registry_hive"] = root_name
                    values["registry_view"] = base
                    entries.append(values)
        except PermissionError:
            raise
        except OSError:
            return []
        return entries

    def _resolve_links(self, paths: list[Path]) -> list[ShortcutRecord]:
        return resolve_links(paths)


class LocalHttpClient(NullHttpClient):
    def get_json(self, url: str, token: str | None = None, timeout: float = 2.0):
        return self._request_json("GET", url, None, token, timeout)

    def post_json(self, url: str, payload, token: str | None = None, timeout: float = 2.0):
        return self._request_json("POST", url, payload, token, timeout)

    def _request_json(self, method: str, url: str, payload, token: str | None, timeout: float):
        headers = {"Host": "127.0.0.1"}
        data = None
        if method == "POST":
            headers["Content-Type"] = "application/json"
            data = json.dumps(payload).encode("utf-8")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            req = request.Request(url, data=data, headers=headers, method=method)
            with request.urlopen(req, timeout=timeout) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            try:
                return exc.code, json.loads(exc.read().decode("utf-8"))
            except Exception:
                return exc.code, {"error": "http_error"}
        except Exception as exc:
            return 0, {"error": type(exc).__name__}


class LocalProcessController(NullProcessController):
    def is_port_open(self, port: int) -> bool:
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            return sock.connect_ex(("127.0.0.1", port)) == 0

    def start_engine(self, exe, args, env, cwd, stdout, stderr) -> ProcessHandle:
        proc, job_error = start_windows_job_process(
            Path(exe), list(args), dict(env), Path(cwd), Path(stdout), Path(stderr)
        )
        if job_error or proc is None:
            return ProcessHandle(0, None, False, job_error)
        return ProcessHandle(proc.pid, proc, True, "")

    def listener_pids(self, port: int) -> list[int]:
        if os.name != "nt":
            return []
        script = ("Get-NetTCPConnection -LocalPort " + str(int(port)) +
                  " -State Listen -ErrorAction SilentlyContinue | "
                  "Select-Object -ExpandProperty OwningProcess | ConvertTo-Json")
        out = subprocess.run(["powershell", "-NoProfile", "-Command", script],
                             text=True, stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL,
                             creationflags=WINDOW_FLAGS)
        if out.returncode != 0 or not out.stdout.strip():
            return []
        data = json.loads(out.stdout)
        return [int(x) for x in (data if isinstance(data, list) else [data])]

    def cleanup(self, handle: ProcessHandle, port: int) -> list[int] | dict:
        captured = self.descendant_processes(handle.pid)
        if handle.job_error:
            return {"state": "FAIL", "surviving_pids": [],
                    "job_object_assigned": False, "job_error": handle.job_error,
                    "captured_descendants": captured, "job_handles_closed": True}
        if hasattr(handle.proc, "terminate_and_verify"):
            return self._cleanup_job(handle, port, captured)
        descendants = [row["pid"] for row in captured]
        proc = handle.proc
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        self._stop_pids(descendants)
        time.sleep(0.2)
        live_times = self.process_creation_times(descendants)
        survivors = _surviving_captured_pids(captured, live_times)
        listeners = self.listener_pids(port) if self.is_port_open(port) else []
        return sorted(set(survivors + listeners))

    def _cleanup_job(self, handle: ProcessHandle, port: int, captured: list[dict]) -> dict:
        proc = handle.proc
        result = proc.terminate_and_verify()
        live_times = self.process_creation_times([int(row["pid"]) for row in captured])
        captured_survivors = _surviving_captured_pids(captured, live_times)
        listeners = self.listener_pids(port) if self.is_port_open(port) else []
        survivors = sorted(set(result["job_active_pids_after"] + captured_survivors + listeners))
        result.update({"job_object_assigned": True, "captured_descendants": captured,
                       "captured_descendant_survivors": captured_survivors,
                       "listener_pids_after": listeners, "surviving_pids": survivors})
        if survivors:
            result["state"] = "FAIL"
        return result

    def descendant_pids(self, pid: int) -> list[int]:
        return [row["pid"] for row in self.descendant_processes(pid)]

    def descendant_processes(self, pid: int) -> list[dict]:
        rows = self._process_rows()
        children: dict[int, list[dict]] = {}
        for row in rows:
            children.setdefault(row["parent_pid"], []).append(row)
        found, stack = [], list(children.get(int(pid), []))
        while stack:
            child = stack.pop()
            if child not in found:
                found.append(child)
                stack.extend(children.get(child["pid"], []))
        return found

    def process_creation_times(self, pids: list[int]) -> dict[int, str]:
        wanted = set(int(pid) for pid in pids)
        return {row["pid"]: row["creation_time"] for row in self._process_rows()
                if row["pid"] in wanted}

    def _process_rows(self) -> list[dict]:
        if os.name != "nt":
            return []
        script = ("Get-CimInstance Win32_Process | "
                  "Select-Object ProcessId,ParentProcessId,CreationDate | ConvertTo-Json")
        out = subprocess.run(["powershell", "-NoProfile", "-Command", script],
                             text=True, stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL,
                             creationflags=WINDOW_FLAGS)
        if out.returncode != 0 or not out.stdout.strip():
            return []
        rows = json.loads(out.stdout)
        out_rows = []
        for row in (rows if isinstance(rows, list) else [rows]):
            out_rows.append({"pid": int(row["ProcessId"]),
                             "parent_pid": int(row["ParentProcessId"]),
                             "creation_time": str(row.get("CreationDate", ""))})
        return out_rows

    def _stop_pids(self, pids: list[int]):
        if not pids or os.name != "nt":
            return
        script = "$args | % { Stop-Process -Id ([int]$_) -Force -ErrorAction SilentlyContinue }"
        subprocess.run(["powershell", "-NoProfile", "-Command", script, *[str(p) for p in pids]],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       creationflags=WINDOW_FLAGS)


def _normalize_appid(value: str) -> str:
    text = value.strip().lower()
    if text.endswith("_is1"):
        text = text[:-4]
    return text.strip("{}")


def _entry_matches_appid(app_id: str, entry: dict) -> bool:
    expected = _normalize_appid(app_id)
    values = [str(entry.get("registry_key", "")), str(entry.get("AppId", "")),
              str(entry.get("Inno Setup: AppId", ""))]
    return any(_normalize_appid(value) == expected for value in values if value)


def _is_flywheel_or_appid_entry(app_id: str, entry: dict) -> bool:
    return entry.get("DisplayName") == "Flywheel" or _entry_matches_appid(app_id, entry)


def _entry_matches_install_root(install_root: Path, entry: dict) -> bool:
    value = entry.get("InstallLocation") or entry.get("InstallDir") or entry.get("InstallRoot")
    if not value:
        return False
    left = os.path.normcase(str(Path(str(value)).expanduser().resolve(strict=False))).rstrip("\\/")
    right = os.path.normcase(str(Path(install_root).expanduser().resolve(strict=False))).rstrip("\\/")
    return left == right


def _surviving_captured_pids(captured: list[dict], live_creation_times: dict[int, str]) -> list[int]:
    if captured and not live_creation_times:
        return [int(row["pid"]) for row in captured]
    return [int(row["pid"]) for row in captured
            if live_creation_times.get(int(row["pid"])) == row.get("creation_time")]
