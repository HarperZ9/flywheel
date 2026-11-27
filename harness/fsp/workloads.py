"""Dummy workloads the demo owns, governed through the Enforcer interface.

The manager starts child processes of this Python interpreter, tags each by
name with a salted workload tag, and acts only on the process handles it
holds. It never looks up, signals or stops any process it did not start.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from .orders import workload_tag

SRC = str(Path(__file__).resolve().parents[2])


class WorkloadManager:
    def __init__(self, run_dir: Path, salt: bytes) -> None:
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.salt = salt
        self.procs: dict[str, subprocess.Popen] = {}
        self.tags: dict[str, str] = {}
        self.state = {"level": 100, "halted_tags": set(), "failed_closed": False}

    def start(self, name: str) -> str:
        tag = workload_tag(self.salt, name)
        if self.state["failed_closed"] or tag in self.state["halted_tags"]:
            raise PermissionError(f"shim refuses new work under tag {tag[:12]}")
        env = dict(os.environ, PYTHONPATH=SRC)
        self._write_level(name, self.state["level"])
        self.procs[name] = subprocess.Popen(
            [sys.executable, "-m", "harness.fsp.workload_child", "--name", name, "--dir",
             str(self.run_dir)], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.tags[name] = tag
        return tag

    def _write_level(self, name: str, level: int) -> None:
        (self.run_dir / f"{name}.level").write_text(str(level), encoding="ascii")

    def running(self, name: str) -> bool:
        proc = self.procs.get(name)
        return proc is not None and proc.poll() is None

    def progress(self, name: str) -> int:
        try:
            return int((self.run_dir / f"{name}.progress").read_text(encoding="ascii") or 0)
        except (OSError, ValueError):
            return 0

    def stop(self, name: str) -> None:
        proc = self.procs[name]
        if proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=10)

    def apply(self, state: dict) -> list[str]:
        self.state = {"level": state["level"], "halted_tags": set(state["halted_tags"]),
                      "failed_closed": state["failed_closed"]}
        for name, tag in self.tags.items():
            if state["failed_closed"] or tag in state["halted_tags"]:
                self.stop(name)
            else:
                self._write_level(name, state["level"])
        return sorted(t for n, t in self.tags.items()
                      if t in state["halted_tags"] and self.running(n))

    def stop_all(self) -> None:
        for name in self.procs:
            self.stop(name)
