"""accountable_hooks.py -- event-triggered automations with teeth.

A registration binds an event type to an argv command (never a shell)
and a blocking flag. Firing an event runs every matching hook through
the real runner, seals a receipt per run, and a failing BLOCKING hook
blocks the event: fail-closed by registration. Secret-shaped commands
and shell invocations are refused at registration; the runner is
argv-only, so there is no interpolation layer to escape through.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from .evidence_json import canonical_sha256

REGISTRATION_SCHEMA = "flywheel.hook-registration/v1"
RUN_SCHEMA = "flywheel.hook-run/v1"

#: The platform's hookable events. Fixed allowlist: an event that is
#: not listed cannot carry automation.
EVENTS = frozenset((
    "bench.completed",
    "journey.stage",
    "agent.completed",
    "route.completed",
    "companion.completed",
    "hook.registered",
    "lesson.admitted",
    "pack.admitted",
))

_SECRET_FRAGMENTS = ("api_key", "apikey", "token", "secret", "password",
                     "credential", "private_key", "authorization")
_SHELL_RUNNERS = ("bash", "sh", "zsh", "cmd", "cmd.exe", "powershell",
                  "powershell.exe", "pwsh", "pwsh.exe")


def _refuse(msg: str) -> None:
    raise ValueError(msg)


def register_hook(*, event: str, argv: list, blocking: bool,
                  hook_id: str, created_at: str) -> dict:
    if event not in EVENTS:
        _refuse(f"unknown event: {event!r}")
    if not isinstance(argv, list) or not argv or any(
            not isinstance(a, str) or not a for a in argv):
        _refuse("a hook command is a non-empty argv list")
    lowered = [a.lower() for a in argv]
    if argv[0].lower() in _SHELL_RUNNERS:
        _refuse(f"shell runners are refused: {argv[0]!r}; "
                "hooks run argv, never a shell")
    joined = " ".join(lowered)
    if any(secret in joined for secret in _SECRET_FRAGMENTS):
        _refuse("the hook command carries secret-shaped text")
    if not isinstance(blocking, bool):
        _refuse("blocking is a boolean")
    if not hook_id.startswith("hook_"):
        _refuse("hook id is not a hook ref")
    reg = {
        "schema": REGISTRATION_SCHEMA,
        "hook_id": hook_id,
        "event": event,
        "argv": list(argv),
        "blocking": blocking,
        "created_at": created_at,
    }
    reg["hook_sha256"] = canonical_sha256(
        {k: v for k, v in reg.items() if k != "hook_sha256"})
    return reg


def run_hooks(event: str, registrations: list[dict], *, runner,
              context: dict) -> list[dict]:
    """Fire every hook registered for `event`. `runner(argv) -> dict`
    with exit_code/output is injectable; production runs argv via
    subprocess with a hard timeout and no shell. A failing BLOCKING hook
    marks the event blocked; non-blocking failures only report."""
    receipts = []
    context_sha = canonical_sha256(context) if context else ""
    for reg in registrations:
        if reg.get("event") != event:
            continue
        started = time.monotonic()
        try:
            outcome = runner(reg["argv"])
            exit_code = int(outcome.get("exit_code", -1))
            output = str(outcome.get("output", ""))
            error = ""
        except TimeoutError:
            exit_code, output, error = -1, "", "timeout"
        except Exception as exc:
            exit_code, output = -1, ""
            error = type(exc).__name__
        receipt = {
            "schema": RUN_SCHEMA,
            "hook_id": reg.get("hook_id", ""),
            "event": event,
            "argv": list(reg.get("argv", [])),
            "blocking": bool(reg.get("blocking")),
            "exit_code": exit_code,
            "output_sha256": hashlib.sha256(output.encode()).hexdigest(),
            "duration_ms": int((time.monotonic() - started) * 1000),
            "context_sha256": context_sha,
            "blocked": bool(reg.get("blocking")) and exit_code != 0,
        }
        if error:
            receipt["error"] = error
        receipts.append(receipt)
    return receipts


def event_blocked(receipts: list[dict]) -> bool:
    return any(r.get("blocked") for r in receipts)


def subprocess_runner(timeout_s: float = 30.0):
    """The production runner: argv via subprocess, no shell, capture,
    hard timeout (raises TimeoutError, which run_hooks seals as a
    failure)."""
    import os
    import subprocess

    def runner(argv: list) -> dict:
        completed = subprocess.run(
            argv, capture_output=True, timeout=timeout_s,
            env={**os.environ, "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"})
        return {
            "exit_code": completed.returncode,
            "output": (completed.stdout + completed.stderr).decode(
                "utf-8", "replace"),
        }

    return runner


def save_registry(registrations: list[dict], *,
                  registry_path: Path) -> Path:
    for reg in registrations:
        if reg.get("schema") != REGISTRATION_SCHEMA:
            _refuse("the registry holds only sealed registrations")
    path = Path(registry_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(registrations, indent=2, sort_keys=True),
                    encoding="utf-8")
    return path


def load_registry(registry_path: Path) -> list[dict]:
    path = Path(registry_path)
    if not path.is_file():
        return []
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        _refuse("the hook registry is not a list")
    for reg in rows:
        if (not isinstance(reg, dict)
                or reg.get("schema") != REGISTRATION_SCHEMA
                or reg.get("event") not in EVENTS):
            _refuse("the hook registry holds an unknown or unsealed row")
    return rows
