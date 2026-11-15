"""Child-process launcher with IO mode injection."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess


def build_io_command(
    python_exe: str,
    io_channel: Path,
    io_mode: str,
    child: list[str],
) -> list[str]:
    if not child:
        raise ValueError("child command is required")
    if io_mode not in {"on", "off"}:
        raise ValueError("io_mode must be on or off")
    toggle = "--IO-on" if io_mode == "on" else "--IO-off"
    return [python_exe, str(io_channel), toggle, "--", *child]


def run_child(
    python_exe: str,
    io_channel: Path,
    io_mode: str,
    child: list[str],
    cwd: Path | None = None,
    extra_env: dict[str, str] | None = None,
) -> int:
    command = build_io_command(python_exe, io_channel, io_mode, child)
    env = os.environ.copy()
    env["WARDEN_PREFIRE_ACTIVE"] = "1"
    if extra_env:
        env.update(extra_env)
    result = subprocess.run(command, cwd=str(cwd) if cwd else None, env=env)
    return result.returncode


def build_launch_env(
    base_env: dict[str, str],
    root: Path,
    state_path: Path,
    receipt_path: Path,
    surface: str,
    host: str,
) -> dict[str, str]:
    env = dict(base_env)
    env.update(
        {
            "WARDEN_PREFIRE_ACTIVE": "1",
            "WARDEN_PREFIRE_ROOT": str(root),
            "WARDEN_PREFIRE_STATE": str(state_path),
            "WARDEN_PREFIRE_RECEIPT": str(receipt_path),
            "WARDEN_PREFIRE_SURFACE": surface,
            "WARDEN_PREFIRE_HOST": host,
        }
    )
    return env
