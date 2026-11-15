#!/usr/bin/env python3
"""Run a command and return its output.

Use this wrapper when an operator or agent needs command output with
predictable capture, timeout, cwd, and stderr handling.

Usage
-----
    # Run a command:
    python tools/safe_exec.py -- rg "pattern" path/

    # Show stderr too:
    python tools/safe_exec.py --include-stderr -- python -m pytest tests/

    # JSON envelope (rc, stdout, stderr, audit_counts):
    python tools/safe_exec.py --json -- git log --oneline -n 50

    # PowerShell shell mode (Windows):
    python tools/safe_exec.py --shell -- "Get-ChildItem AGENTS\\warden_shell"

    # Timeout (seconds):
    python tools/safe_exec.py --timeout 30 -- ./long_running.sh

    # Audit-only (do not run; useful for hook ordering tests):
    python tools/safe_exec.py --dry-run -- ls -la

Behavior
--------
* Default behavior emits stdout. Stderr is captured but not emitted unless
  ``--include-stderr`` is set.
* Return-code preservation: safe_exec exits with the child process's exit
  code so callers can compose it inside shell pipelines.
* No shell metacharacter expansion by default — argv list goes straight
  to subprocess.run with shell=False. --shell opts in (Windows defaults
  to cmd.exe / PowerShell as configured; POSIX defaults to /bin/sh).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Iterable

from io_state import add_io_toggle_args, transforms_enabled
from _core import build_engine


_ROOT = Path(__file__).resolve().parent


def _archive_raw(cmd_repr: str, stdout: bytes, stderr: bytes) -> Path:
    digest = hashlib.sha256(cmd_repr.encode("utf-8")).hexdigest()[:24]
    base = Path.cwd() / ".warden-safe-cache" / "exec"
    base.mkdir(parents=True, exist_ok=True)
    raw_path = base / f"{digest}.raw"
    raw_path.write_bytes(
        b"# ---- stdout ----\n" + stdout
        + b"\n# ---- stderr ----\n" + stderr
    )
    return raw_path


def _run(
    argv: list[str],
    *,
    timeout: float | None,
    shell: bool,
    cwd: str | None,
) -> tuple[int, bytes, bytes]:
    try:
        proc = subprocess.run(
            argv if not shell else " ".join(argv),
            shell=shell,
            capture_output=True,
            timeout=timeout,
            cwd=cwd,
            check=False,
        )
        return proc.returncode, proc.stdout or b"", proc.stderr or b""
    except subprocess.TimeoutExpired as e:
        out = e.stdout or b""
        err = (e.stderr or b"") + f"\nsafe_exec: timeout after {timeout}s\n".encode("utf-8")
        return 124, out, err
    except FileNotFoundError as e:
        return 127, b"", f"safe_exec: command not found: {e}\n".encode("utf-8")


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run a subprocess and emit stdout/stderr."
        ),
        usage="safe_exec.py [options] -- CMD [ARG ...]",
    )
    parser.add_argument(
        "--include-stderr",
        action="store_true",
        help="Emit stderr after stdout.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a JSON envelope: {rc, stdout, stderr, audit_counts, total}.",
    )
    parser.add_argument(
        "--diff-only",
        action="store_true",
        help="Emit audit counters only (no captured output).",
    )
    parser.add_argument(
        "--shell",
        action="store_true",
        help="Run via the system shell (cmd/sh). Default is direct argv.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=None,
        help="Kill the child after N seconds (default: no timeout).",
    )
    parser.add_argument(
        "--cwd",
        type=str,
        default=None,
        help="Working directory for the child process.",
    )
    parser.add_argument(
        "--no-archive",
        action="store_true",
        help="Do not archive raw stdout/stderr under .warden-safe-cache/exec/.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the would-be argv to stdout; do not execute.",
    )
    add_io_toggle_args(parser)
    parser.add_argument(
        "cmd",
        nargs=argparse.REMAINDER,
        help="Command and arguments to execute. Place after `--`.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    cmd = list(args.cmd)
    # argparse REMAINDER may include the literal `--`. Strip it.
    while cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if not cmd:
        parser.error("no command given (use: safe_exec.py [opts] -- CMD [ARG ...])")

    io_on = transforms_enabled(args)

    if args.dry_run:
        sys.stdout.write(
            json.dumps(
                {
                    "dry_run": True,
                    "argv": cmd,
                    "shell": bool(args.shell),
                    "cwd": args.cwd,
                    "timeout": args.timeout,
                    "io_channel": "on" if io_on else "off",
                },
                indent=2,
            )
            + "\n"
        )
        return 0

    cmd_repr = " ".join(cmd)
    rc, stdout_b, stderr_b = _run(
        cmd,
        timeout=args.timeout,
        shell=args.shell,
        cwd=args.cwd,
    )

    if not args.no_archive:
        try:
            _archive_raw(cmd_repr, stdout_b, stderr_b)
        except OSError:
            pass  # archiving is best-effort; never block on it

    stdout_t = stdout_b.decode("utf-8", errors="replace")
    stderr_t = stderr_b.decode("utf-8", errors="replace")

    if io_on:
        engine = build_engine()
        stdout_text, out_t1, out_t2 = engine.apply(stdout_t)
        stderr_text, err_t1, err_t2 = engine.apply(stderr_t)
        out_counter = {"tier1": out_t1, "tier2": out_t2}
        err_counter = {"tier1": err_t1, "tier2": err_t2}
    else:
        stdout_text, stderr_text = stdout_t, stderr_t
        out_counter = {"tier1": 0, "tier2": 0}
        err_counter = {"tier1": 0, "tier2": 0}
    counts = {
        "tier1": out_counter["tier1"] + err_counter["tier1"],
        "tier2": out_counter["tier2"] + err_counter["tier2"],
    }
    total = sum(counts.values())

    if args.diff_only:
        sys.stdout.write(
            json.dumps(
                {
                    "argv": cmd,
                    "rc": rc,
                    "audit_counts": counts,
                    "total": total,
                    "io_channel": "on" if io_on else "off",
                    "by_stream": {
                        "stdout": dict(out_counter),
                        "stderr": dict(err_counter),
                    },
                },
                indent=2,
            )
            + "\n"
        )
        return rc

    if args.json:
        sys.stdout.write(
            json.dumps(
                {
                    "argv": cmd,
                    "rc": rc,
                    "stdout": stdout_text,
                    "stderr": stderr_text,
                    "audit_counts": counts,
                    "total": total,
                    "io_channel": "on" if io_on else "off",
                },
                indent=2,
            )
            + "\n"
        )
        return rc

    # Reconfigure stdout to UTF-8 — same defensive shape as safe_read.
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass
    try:
        sys.stdout.write(stdout_text)
    except UnicodeEncodeError:
        buf = getattr(sys.stdout, "buffer", None)
        if buf is not None:
            buf.write(stdout_text.encode("utf-8", errors="replace"))
    if not stdout_text.endswith("\n"):
        sys.stdout.write("\n")
    if args.include_stderr and stderr_text.strip():
        sys.stdout.write("# ---- stderr ----\n")
        sys.stdout.write(stderr_text)
        if not stderr_text.endswith("\n"):
            sys.stdout.write("\n")

    return rc


if __name__ == "__main__":
    raise SystemExit(main())
