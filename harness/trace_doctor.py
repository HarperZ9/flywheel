"""`flywheel traces doctor`: is capture working, and what is it doing? (7.1)

Twelve checks, each PASS, WARN, FAIL or UNKNOWN with one line of remedy:
hook mounts, hook interpreters, the token, the capture channel (home,
endpoint, listener, proof and a signed ping), capture settings, spooled
failures and suppressions, client retention, encryption, presence and the
witness, disk and backup facts, where the home lives, and a synthetic turn.

Nothing taken from a settings file is ever run. `--synthetic` runs the
Flywheel hook module itself with a synthetic event. `--ack` moves the
reported failure records aside.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import os
from pathlib import Path

from . import trace_doctor_checks as checks
from .trace_cli_text import escape

SCHEMA = "flywheel.trace-doctor/v1"


@dataclass(frozen=True)
class Check:
    number: int
    name: str
    state: str
    detail: str
    remedy: str = ""


def _mounts(environ, cwd):
    from .trace_doctor_mounts import scan
    mounts, read, names = scan(environ, cwd)
    broken = [m for m in mounts if m.problem]
    listed = "; ".join(f"{m.label}: {m.event} -> {m.target} ({m.form}"
                       f"{', ' + m.problem if m.problem else ''})" for m in mounts)
    detail = (listed or "no Flywheel hook mount found") + (
        f"; files read: {', '.join(read)}" if read else "; no settings file found")
    detail += "; managed policy files not checked"
    if names:
        detail += f"; env blocks set {', '.join(names)}"
    if broken:
        return "FAIL", detail, "flywheel traces hooks print-mount, then fix the mount"
    if not mounts or all(m.form == "legacy-script" for m in mounts):
        return "WARN", detail, "flywheel traces hooks print-mount"
    return "PASS", detail, ""


def _interpreters(environ, cwd):
    from .trace_doctor_mounts import scan
    mounts = [m for m in scan(environ, cwd)[0] if m.form == "module"]
    if not mounts:
        return "UNKNOWN", "no module mount to check", "flywheel traces hooks print-mount"
    missing = [m for m in mounts if m.problem == "interpreter not found"]
    if missing:
        return "FAIL", f"{len(missing)} mount(s) name an interpreter that is not there", (
            "flywheel traces hooks print-mount")
    return ("PASS", f"{len(mounts)} mount(s) name an existing interpreter; its version is "
            "not checked, since that would run a program named in a settings file", "")


def run_doctor(home, *, environ=None, cwd=None, synthetic=False, ack=False) -> list[Check]:
    home = Path(home)
    environ = dict(os.environ if environ is None else environ)
    cwd = Path(cwd or os.getcwd())
    results = [
        ("hook mounts", _mounts(environ, cwd)),
        ("hook interpreters", _interpreters(environ, cwd)),
        ("gateway token", checks.token_check(home)),
        ("capture channel", checks.channel_check(home, environ, cwd)),
        ("capture settings", checks.settings_check(home)),
        ("capture failures", checks.failures_check(home, ack)),
        ("client retention", checks.retention_check(environ, cwd)),
        ("encryption", checks.encryption_check(home)),
        ("presence and witness", checks.presence_check(home)),
        ("disk and backup", checks.disk_check(home)),
        ("home location", checks.location_check(home, environ)),
        ("synthetic turn", checks.synthetic_check(home, synthetic)),
    ]
    return [Check(i, name, *result) for i, (name, result) in enumerate(results, 1)]


def render(results: list[Check]) -> list[str]:
    lines = ["Flywheel trace doctor"]
    for check in results:
        lines.append(f"{check.number:>2}. {check.state:<7} {check.name}: {escape(check.detail)}")
        if check.remedy:
            lines.append(f"    next: {check.remedy}")
    return lines


def to_json(results: list[Check]) -> dict:
    return {"schema": SCHEMA, "checks": [asdict(c) for c in results]}


def print_mount() -> list[str]:
    """The exact mount lines, with this interpreter's absolute path."""
    import json
    import sys
    base = f'"{sys.executable}" -m harness.capture_hooks'

    def block(client):
        events = (("UserPromptSubmit", "prompt"), ("Stop", "stop"), ("SessionEnd", "session-end"))
        return {"hooks": {event: [{"hooks": [{"type": "command",
                "command": f"{base} {arg} --client {client}"}]}] for event, arg in events}}
    return ["Claude Code (settings.json):", json.dumps(block("claude-code"), indent=2), "",
            "Codex (hooks.json):", json.dumps(block("codex"), indent=2), "",
            "Flywheel never edits client settings. Paste one block into the client's file."]
