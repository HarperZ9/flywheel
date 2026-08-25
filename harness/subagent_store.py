"""subagent_store.py -- where swarms persist and how children launch.

Receipts live under <run_root>/subagents/<swarm_id>/; the sealed
fan-in receipt is the only thing allowed to persist there. Children
launch as argv process trees (never a shell) with the package root on
PYTHONPATH, their own cwd, and a hard timeout enforced by the caller.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from .subagent_roles import SWARM_SCHEMA

LIVE_SCHEMA = "flywheel.subagent-live/v1"

_PKG_ROOT = str(Path(__file__).resolve().parent.parent)


def _refuse(msg: str) -> None:
    raise ValueError(msg)


def swarm_dir(run_root: Path, swarm_id: str) -> Path:
    return Path(run_root) / "subagents" / str(swarm_id)


def save_swarm_receipt(receipt: dict, *, run_root: Path) -> Path:
    if receipt.get("schema") != SWARM_SCHEMA:
        _refuse("only a sealed swarm receipt persists here")
    path = swarm_dir(run_root, receipt["swarm_id"]) / "swarm.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(receipt, indent=2, sort_keys=True),
                    encoding="utf-8")
    return path


def load_swarm_receipt(path: Path) -> "dict | None":
    p = Path(path)
    if not p.is_file():
        return None
    receipt = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(receipt, dict) \
            or receipt.get("schema") != SWARM_SCHEMA:
        _refuse("the persisted swarm receipt is not a swarm receipt")
    return receipt


def save_live_state(live: dict, *, run_root: Path) -> Path:
    if live.get("schema") != LIVE_SCHEMA:
        _refuse("only a live-state record persists here")
    path = swarm_dir(run_root, live["swarm_id"]) / "live.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(live, indent=2, sort_keys=True),
                    encoding="utf-8")
    return path


def load_live_state(path: Path) -> "dict | None":
    p = Path(path)
    if not p.is_file():
        return None
    live = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(live, dict) or live.get("schema") != LIVE_SCHEMA \
            or not isinstance(live.get("children"), list):
        _refuse("the persisted live state is not a live state record")
    return live


def detached_summaries(run_root: Path) -> list[dict]:
    """Swarms with a live state but no sealed receipt: the restart case."""
    root = Path(run_root) / "subagents"
    rows = []
    if root.is_dir():
        for entry in sorted(root.iterdir()):
            if (entry / "swarm.json").is_file():
                continue
            live = load_live_state(entry / "live.json")
            if live is not None:
                rows.append({"swarm_id": entry.name,
                             "status": "detached",
                             "children": len(live["children"])})
    return rows


def _summary(receipt: dict) -> dict:
    kids = receipt.get("children", [])
    done = sum(1 for k in kids if k.get("status") == "completed")
    return {"swarm_id": receipt.get("swarm_id"), "status": "sealed",
            "verdict": receipt.get("verdict"), "completed": done,
            "total": len(kids),
            "event_blocked": bool(receipt.get("event_blocked"))}


def sealed_summaries(run_root: Path) -> list[dict]:
    root = Path(run_root) / "subagents"
    rows = []
    if root.is_dir():
        for entry in sorted(root.iterdir()):
            receipt = load_swarm_receipt(entry / "swarm.json")
            if receipt:
                rows.append(_summary(receipt))
    return rows


def worker_command(spec_path: Path) -> list:
    return [sys.executable, "-m", "harness.subagent_worker", str(spec_path)]


def child_env() -> dict:
    existing = os.environ.get("PYTHONPATH", "")
    return {**os.environ,
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
            "PYTHONPATH": _PKG_ROOT + (os.pathsep + existing if existing
                                       else "")}


class _PopenHandle:
    def __init__(self, proc: "subprocess.Popen") -> None:
        self._proc = proc

    @property
    def pid(self) -> "int | None":
        return self._proc.pid

    def wait(self, timeout_s: float) -> tuple[int, str]:
        try:
            out, err = self._proc.communicate(timeout=float(timeout_s))
        except subprocess.TimeoutExpired:
            raise TimeoutError from None
        raw = (out or b"") + (err or b"")
        return int(self._proc.returncode or 0), raw.decode("utf-8", "replace")

    def stop(self) -> bool:
        try:
            self._proc.kill()
            self._proc.communicate(timeout=5)
        except Exception:
            pass
        return True


def popen_handle(spec_path: Path, workspace: Path) -> _PopenHandle:
    """The production child launcher: argv only, no shell, own cwd."""
    workspace.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        worker_command(Path(spec_path)), cwd=str(workspace),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=child_env())
    return _PopenHandle(proc)
