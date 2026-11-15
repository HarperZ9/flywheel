#!/usr/bin/env python3
"""
IO Channel - Universal passthrough container.

Architecture: [A -> Container -> CLI/Harness -> Container -> B]

  A           = operator stdin (keystrokes, piped bytes, line input)
  Container   = this module (applies vocabulary calibration)
  CLI/Harness = WARDEN CLI, Claude Code, Codex, or any shell command
  B           = calibrated output returned to the operator terminal

Stdin bytes from the operator are calibrated via safe_input vocabulary
child safety assessment before reaching the CLI/Harness. Stdout from the CLI/Harness is
calibrated via safe_exec vocabulary child safety assessment before reaching the operator.
Both channels share vocabulary_map.py CALIBRATIONS - calibration is
symmetric and idempotent.

Single-workstation, owner-operator mode. No network calls; all bytes
stay local and pass through this container only.

Usage
-----
    python io_channel.py -- claude --print "task description"
    python io_channel.py -- warden scan --dir .
    python io_channel.py -- codex run
    echo "raw input" | python io_channel.py -- claude --print -
    python io_channel.py --include-stderr -- warden check
    python io_channel.py --report -- warden scan
    python io_channel.py --dry-run -- claude --help
    python io_channel.py --no-calibrate -- claude --help

Operating mode
--------------
Three threads for concurrent pipe forwarding:
  Thread-1 (stdin):  reads operator stdin line-by-line, calibrates each
                     line, writes calibrated bytes to child stdin.
  Thread-2 (stdout): reads child stdout in 4 KB chunks, calibrates on
                     newline boundaries, writes to operator stdout.
  Thread-3 (stderr): active only with --include-stderr; otherwise child
                     stderr routes to DEVNULL.

On Windows, subprocess is created with CREATE_NEW_PROCESS_GROUP so
that Ctrl+C propagates correctly to the child.

Archives
--------
  Pre-calibration stdin lines: .warden-safe-cache/io_channel/stdin/<sha>.raw
  Substitution report:         .warden-safe-cache/io_channel/report/<sha>.json
  (use --no-archive to skip both)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
from collections import Counter
from pathlib import Path
from typing import IO, Iterable

from io_state import add_io_toggle_args, env_mode, set_env_mode, split_io_toggles

_TOOLS_ROOT = Path(__file__).resolve().parent


# --- Calibration -------------------------------------------------------------

def _load_vocab_map() -> dict:
    import importlib.util
    bt = os.environ.get("BEHAVIOR_TRANSFORM_TOOLS", "").strip()
    if bt:
        p = Path(bt) / "vocabulary_map.py"
        if p.is_file():
            spec = importlib.util.spec_from_file_location("_vm_iochan", p)
            if spec is not None and spec.loader is not None:
                mod = importlib.util.module_from_spec(spec)
                sys.modules["_vm_iochan"] = mod
                try:
                    spec.loader.exec_module(mod)
                    return mod.__dict__
                except Exception:
                    sys.modules.pop("_vm_iochan", None)
    p = Path(__file__).resolve().parent / "vocabulary_map.py"
    if p.is_file():
        spec = importlib.util.spec_from_file_location("_vm_iochan", p)
        if spec is not None and spec.loader is not None:
            mod = importlib.util.module_from_spec(spec)
            sys.modules["_vm_iochan"] = mod
            try:
                spec.loader.exec_module(mod)
                return mod.__dict__
            except Exception:
                sys.modules.pop("_vm_iochan", None)
    return {}


def _build_subs(vm: dict) -> list:
    calibrations = vm.get("CALIBRATIONS", ())
    keep = {k.lower() for k in (vm.get("KEEP_TERMS", None) or [])}
    candidates = []
    for c in calibrations:
        original = getattr(c, "original", None)
        calibrated_form = getattr(c, "calibrated", None)
        severity = (getattr(c, "severity", "") or "").lower()
        if not isinstance(original, str) or not isinstance(calibrated_form, str):
            continue
        if original.lower() in keep:
            continue
        tier = (
            "T1" if severity in ("tier1", "tier_1", "t1") else
            "T2" if severity in ("tier2", "tier_2", "t2") else
            severity.upper() or "??"
        )
        candidates.append((original, calibrated_form, tier))
    candidates.sort(key=lambda t: len(t[0]), reverse=True)
    return [
        (re.compile(r"\b" + re.escape(src) + r"\b", re.IGNORECASE), dst, tier)
        for src, dst, tier in candidates
    ]


def _calibrate(text: str, subs: list) -> tuple:
    counter: Counter = Counter()
    for pat, dst, tier in subs:
        def _repl(m: re.Match, _d: str = dst, _t: str = tier) -> str:
            counter[_t] += 1
            return _d
        text = pat.sub(_repl, text)
    return text, counter


# --- Archive -----------------------------------------------------------------

def _archive(subdir: str, key: str, content: str) -> None:
    try:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
        base = Path.cwd() / ".warden-safe-cache" / "io_channel" / subdir
        base.mkdir(parents=True, exist_ok=True)
        (base / (digest + ".raw")).write_text(content, encoding="utf-8")
    except OSError:
        pass


# --- Forwarding Threads ------------------------------------------------------

def _stdin_forwarder(
    proc: subprocess.Popen,
    subs: list,
    counter: Counter,
    no_archive: bool,
    no_calibrate: bool,
) -> None:
    """Read operator stdin line-by-line, calibrate, forward to child stdin."""
    try:
        for line in sys.stdin:
            if no_calibrate:
                cal = line
            else:
                cal, cnt = _calibrate(line, subs)
                counter.update(cnt)
                if not no_archive and cnt:
                    _archive("stdin", line, line)
            if proc.stdin is not None and not proc.stdin.closed:
                try:
                    proc.stdin.write(cal.encode("utf-8", errors="replace"))
                    proc.stdin.flush()
                except (OSError, BrokenPipeError):
                    break
    except (OSError, ValueError):
        pass
    finally:
        if proc.stdin is not None and not proc.stdin.closed:
            try:
                proc.stdin.close()
            except OSError:
                pass


def _stream_forwarder(
    source: IO,
    dest: IO,
    subs: list,
    counter: Counter,
    no_calibrate: bool,
) -> None:
    """Read byte stream in 4 KB chunks, calibrate on newline boundaries, write to dest."""
    buf = bytearray()
    try:
        while True:
            chunk = source.read(4096)
            if not chunk:
                break
            buf.extend(chunk)
            while b"\n" in buf:
                idx = buf.index(b"\n")
                line = buf[: idx + 1].decode("utf-8", errors="replace")
                buf = buf[idx + 1:]
                if not no_calibrate:
                    cal, cnt = _calibrate(line, subs)
                    counter.update(cnt)
                else:
                    cal = line
                try:
                    dest.write(cal)
                    dest.flush()
                except (OSError, BrokenPipeError):
                    return
        if buf:
            text = buf.decode("utf-8", errors="replace")
            if not no_calibrate:
                cal, cnt = _calibrate(text, subs)
                counter.update(cnt)
            else:
                cal = text
            try:
                dest.write(cal)
                dest.flush()
            except (OSError, BrokenPipeError):
                pass
    except (OSError, ValueError):
        pass


# --- Container ---------------------------------------------------------------

def _run_container(
    cmd: list,
    subs: list,
    cwd,
    timeout,
    shell: bool,
    no_archive: bool,
    no_calibrate: bool,
    include_stderr: bool,
) -> tuple:
    """Launch child process, run three forwarding threads. Returns (rc, counters)."""
    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP

    try:
        proc = subprocess.Popen(
            " ".join(cmd) if shell else cmd,
            shell=shell,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE if include_stderr else subprocess.DEVNULL,
            cwd=cwd,
            creationflags=creationflags,
        )
    except FileNotFoundError:
        sys.stderr.write("io_channel: command not found: " + repr(cmd[0]) + "\n")
        return 127, Counter(), Counter(), Counter()
    except OSError as exc:
        sys.stderr.write("io_channel: failed to launch " + repr(cmd[0]) + ": " + str(exc) + "\n")
        return 1, Counter(), Counter(), Counter()

    stdin_cnt: Counter = Counter()
    stdout_cnt: Counter = Counter()
    stderr_cnt: Counter = Counter()

    t_stdin = threading.Thread(
        target=_stdin_forwarder,
        args=(proc, subs, stdin_cnt, no_archive, no_calibrate),
        daemon=True,
        name="iochan-stdin",
    )
    assert proc.stdout is not None
    t_stdout = threading.Thread(
        target=_stream_forwarder,
        args=(proc.stdout, sys.stdout, subs, stdout_cnt, no_calibrate),
        daemon=True,
        name="iochan-stdout",
    )

    active_threads = [t_stdin, t_stdout]

    if include_stderr and proc.stderr is not None:
        t_stderr = threading.Thread(
            target=_stream_forwarder,
            args=(proc.stderr, sys.stderr, subs, stderr_cnt, no_calibrate),
            daemon=True,
            name="iochan-stderr",
        )
        active_threads.append(t_stderr)

    for t in active_threads:
        t.start()

    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        return 124, stdin_cnt, stdout_cnt, stderr_cnt

    for t in active_threads[1:]:
        t.join(timeout=10)

    rc = proc.returncode if proc.returncode is not None else 0
    return rc, stdin_cnt, stdout_cnt, stderr_cnt


# --- Entry Point -------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="IO Channel: calibrated passthrough container for CLI/Harness tools.",
        usage="io_channel.py [options] -- CMD [ARG ...]",
    )
    parser.add_argument("--include-stderr", action="store_true",
                        help="Calibrate and emit child stderr alongside stdout.")
    parser.add_argument("--shell", action="store_true",
                        help="Execute via system shell (cmd.exe on Windows).")
    parser.add_argument("--timeout", type=float, default=None,
                        help="Kill child after N seconds (exit code 124 on timeout).")
    parser.add_argument("--cwd", type=str, default=None,
                        help="Working directory for the child process.")
    parser.add_argument("--no-archive", action="store_true",
                        help="Skip .warden-safe-cache/io_channel/ pre-calibration snapshots.")
    parser.add_argument("--no-calibrate", action="store_true",
                        help="Pass-through without vocabulary calibration. Testing/bypass only.")
    add_io_toggle_args(parser)
    parser.add_argument("--report", action="store_true",
                        help="Emit JSON substitution report to stderr after execution.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print the would-be command as JSON; do not execute.")
    parser.add_argument("cmd", nargs=argparse.REMAINDER,
                        help="Command and arguments. Place after '--'.")
    args = parser.parse_args(list(argv) if argv is not None else None)

    cmd = list(args.cmd)
    while cmd and cmd[0] == "--":
        cmd = cmd[1:]
    cmd_mode, cmd = split_io_toggles(cmd)
    while cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if not cmd:
        parser.error("no command given -- usage: io_channel.py [opts] -- CMD [ARG ...]")

    explicit_mode = args.io_channel or cmd_mode
    if explicit_mode is not None:
        set_env_mode(explicit_mode)
    io_on = (explicit_mode or env_mode()) == "on"
    no_calibrate = bool(args.no_calibrate or not io_on)

    if args.dry_run:
        sys.stdout.write(json.dumps({
            "dry_run": True,
            "cmd": cmd,
            "shell": bool(args.shell),
            "cwd": args.cwd,
            "timeout": args.timeout,
            "calibrate": not no_calibrate,
            "io_channel": "on" if not no_calibrate else "off",
        }, indent=2) + "\n")
        return 0

    vm = _load_vocab_map() if not no_calibrate else {}
    subs = _build_subs(vm) if not no_calibrate else []

    rc, stdin_cnt, stdout_cnt, stderr_cnt = _run_container(
        cmd, subs,
        cwd=args.cwd,
        timeout=args.timeout,
        shell=args.shell,
        no_archive=args.no_archive,
        no_calibrate=no_calibrate,
        include_stderr=args.include_stderr,
    )

    if args.report:
        total = (sum(stdin_cnt.values()) + sum(stdout_cnt.values())
                 + sum(stderr_cnt.values()))
        report = {
            "cmd": cmd,
            "rc": rc,
            "calibrated": not no_calibrate,
            "io_channel": "on" if not no_calibrate else "off",
            "substitutions": {
                "stdin":  dict(stdin_cnt),
                "stdout": dict(stdout_cnt),
                "stderr": dict(stderr_cnt),
            },
            "total": total,
        }
        if not args.no_archive:
            _archive("report", " ".join(cmd), json.dumps(report))
        sys.stderr.write("# io_channel: " + json.dumps(report) + "\n")

    return rc


if __name__ == "__main__":
    raise SystemExit(main())
