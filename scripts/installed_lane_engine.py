"""Start and watch the installed engine the way the desktop app starts it.

The app runs ``<install>/engine/flywheel-gateway.exe --port <free>
--desktop-launch`` with the install folder as its working directory
(``desktop/lib/services/gateway_process.dart``). The acceptance does the same
under a throwaway profile: a stripped environment whose PATH is the system
folder only, and whose home, profile, app data and temp folders all sit under
one throwaway root. Nothing from the caller's environment is inherited, so a
key or tool the build machine has cannot reach the engine by accident.

The gateway token is read from ``<home>/gateway.token`` into memory only.
"""
from __future__ import annotations

import os
from pathlib import Path
import socket
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable, Iterable

ENV_NAMES = frozenset((
    "SYSTEMROOT", "WINDIR", "PATH", "FLYWHEEL_HOME", "USERPROFILE", "APPDATA",
    "LOCALAPPDATA", "TEMP", "TMP", "FLYWHEEL_GIT"))
_NO_WINDOW = 0x08000000


def profile_env(root: Path, *, git: str | None, systemroot: str | None = None) -> dict:
    """The engine's whole environment: system folder PATH, throwaway profile.

    ``git`` None sets ``FLYWHEEL_GIT=none`` (the no-Git state on a machine that
    has Git); a path points discovery at that git.exe (the setup leg). Node is
    left to the engine: the installed build bundles it (O-1).
    """
    sysroot = systemroot or os.environ.get("SYSTEMROOT", r"C:\Windows")
    profile = root / "profile"
    return {
        "SYSTEMROOT": sysroot, "WINDIR": sysroot, "PATH": sysroot + r"\System32",
        "FLYWHEEL_HOME": str(root / "home"), "USERPROFILE": str(profile),
        "APPDATA": str(profile / "AppData" / "Roaming"),
        "LOCALAPPDATA": str(profile / "AppData" / "Local"),
        "TEMP": str(root / "tmp"), "TMP": str(root / "tmp"),
        "FLYWHEEL_GIT": git or "none",
    }


def make_profile_dirs(env: dict) -> None:
    for name in ("FLYWHEEL_HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "TEMP"):
        Path(env[name]).mkdir(parents=True, exist_ok=True)


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@dataclass
class RunningEngine:
    proc: subprocess.Popen
    base: str
    token: str
    home: Path


def start_engine(install_root: Path, env: dict, *, timeout_s: float = 120.0) -> RunningEngine:
    """Start the installed engine and wait for its token and first answer."""
    make_profile_dirs(env)
    exe = install_root / "engine" / "flywheel-gateway.exe"
    port = free_port()
    proc = subprocess.Popen([str(exe), "--port", str(port), "--desktop-launch"],
                            cwd=str(install_root), env=env, stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            creationflags=_NO_WINDOW if os.name == "nt" else 0)
    base = f"http://127.0.0.1:{port}"
    token_file = Path(env["FLYWHEEL_HOME"]) / "gateway.token"
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"engine exited during start with code {proc.returncode}")
        if token_file.is_file() and _answers(base):
            token = token_file.read_text(encoding="utf-8").strip()
            return RunningEngine(proc, base, token, Path(env["FLYWHEEL_HOME"]))
        time.sleep(0.5)
    stop_engine(proc)
    raise RuntimeError("engine did not answer within the start timeout")


def _answers(base: str) -> bool:
    """True once the engine answers HTTP at all (401 without a token counts)."""
    try:
        urllib.request.urlopen(base + "/llms.txt", timeout=2).close()
    except urllib.error.HTTPError:
        return True
    except OSError:
        return False
    return True


def stop_engine(proc: subprocess.Popen) -> None:
    """Stop the engine and its lane children."""
    if proc.poll() is None:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                       capture_output=True, check=False)
    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()


def tree_snapshot(root: Path) -> dict[str, tuple[int, int]]:
    """Every file under ``root``: relative posix path -> (size, mtime_ns)."""
    out = {}
    for path in sorted(Path(root).rglob("*")):
        if path.is_file():
            stat = path.stat()
            out[path.relative_to(root).as_posix()] = (stat.st_size, stat.st_mtime_ns)
    return out


def tree_changes(before: dict, after: dict) -> dict[str, list[str]]:
    return {"added": sorted(set(after) - set(before)),
            "removed": sorted(set(before) - set(after)),
            "changed": sorted(k for k in set(before) & set(after) if before[k] != after[k])}


def states_of(roster: dict) -> dict[str, tuple]:
    return {row.get("name"): (row.get("state"), row.get("code"))
            for row in (roster or {}).get("lanes", []) if isinstance(row, dict)}


def d1_unchanged(rosters: Iterable[dict]) -> bool:
    """True when every roster read reports the same state and code per lane."""
    seen = [states_of(r) for r in rosters]
    return bool(seen) and all(s == seen[0] for s in seen[1:])


def wait_settled(fetch: Callable[[], dict], *, quiet_s: float = 15.0, limit_s: float = 240.0,
                 clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep, poll_s: float = 2.0) -> dict:
    """Poll the roster until its states hold still for ``quiet_s``."""
    start = clock()
    roster = fetch()
    last, changed_at = states_of(roster), clock()
    while clock() - start < limit_s:
        sleep(poll_s)
        roster = fetch()
        now = states_of(roster)
        if now != last:
            last, changed_at = now, clock()
        elif clock() - changed_at >= quiet_s:
            return {"settled": True, "seconds": round(clock() - start, 1), "roster": roster}
    return {"settled": False, "seconds": round(clock() - start, 1), "roster": roster}
