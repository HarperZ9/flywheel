"""flywheel_guards.py -- the guards Flywheel already ships, applied to these calls.

  d1_denylist   harness.local_tools.ToolGate: the regex denylist on shell commands.
  d2_shell      harness.shell_admission.classify_command: capability-typed shell
                admission; BLOCK and ESCALATE both count as a stop.
  d3_preaction  harness.preaction.rules: the pre-action monitor's rule layer
                (layer 1 only; no judge, no trajectory state). HOLD and BLOCK
                both count as a stop.

d1 and d2 read shell text only, so a call through a structured tool (delete_path,
http_request) reaches them only as the shell command an adapter would write for
it. d3 reads Claude-Code-shaped calls. The adapter below is ours, not part of
those modules, and every translation it makes is listed in `as_shell`.
"""
from __future__ import annotations

import shlex

from harness.local_tools import ToolGate
from harness.preaction.contract import ProposedCall, RunContext
from harness.preaction.rules import evaluate, load_pack
from harness.shell_admission import classify_command

_GATE = ToolGate(allow_write=True, allow_exec=True)
_PACK = load_pack()


def as_shell(name: str, args) -> str | None:
    """The shell command a harness adapter would emit for this call, if any."""
    a = args if isinstance(args, dict) else {}
    q = lambda k: shlex.quote(str(a.get(k, "")))  # noqa: E731
    if name == "run_shell":
        return str(a.get("command", ""))
    if name == "schedule_cron":
        return str(a.get("command", ""))
    if name == "delete_path":
        return f"rm {'-rf ' if a.get('recursive') else ''}{q('path')}"
    if name == "move_path":
        return f"mv {q('src')} {q('dst')}"
    if name == "copy_path":
        return f"cp -r {q('src')} {q('dst')}"
    if name == "set_permissions":
        return f"chmod {q('mode')} {q('path')}"
    if name == "remove_cron":
        return f"crontab -l | grep -v {q('name')} | crontab -"
    if name == "http_request" and str(a.get("method", "GET")).upper() != "GET":
        return f"curl -X {q('method')} {q('url')} --data {q('body')}"
    if name == "git":
        return "git " + " ".join(shlex.quote(str(x)) for x in a.get("args", []))
    return None


def d1_denylist(name: str, args, intent: dict) -> str | None:
    cmd = as_shell(name, args)
    return None if cmd is None else _GATE.check("run", {"cmd": cmd})


def d2_shell(name: str, args, intent: dict) -> str | None:
    cmd = as_shell(name, args)
    if cmd is None:
        return None
    decision = classify_command(cmd)
    return None if decision.allowed else decision.reason_code


def _proposed(name: str, args) -> ProposedCall:
    a = args if isinstance(args, dict) else {}
    if name == "write_file":
        return ProposedCall(tool="Write", args={"file_path": str(a.get("path", "")),
                                                "content": str(a.get("content", ""))})
    if name in ("read_file", "list_dir", "list_cron"):
        return ProposedCall(tool="Read", args={"file_path": str(a.get("path", ""))})
    if name == "http_request" and str(a.get("method", "GET")).upper() == "GET":
        return ProposedCall(tool="WebFetch", args={"url": str(a.get("url", ""))})
    cmd = as_shell(name, args)
    return ProposedCall(tool="Bash", args={"command": cmd or ""})


def d3_preaction(name: str, args, intent: dict) -> str | None:
    ctx = RunContext(run_id="agent-false-accept", goal=intent.get("request", ""),
                     workspace="/workspace")
    hits = [h for h in evaluate(_PACK, _proposed(name, args), ctx)
            if h.action in ("BLOCK", "HOLD")]
    return hits[0].id if hits else None


FLYWHEEL_GUARDS = {"d1_denylist": d1_denylist, "d2_shell_admission": d2_shell,
                   "d3_preaction_rules": d3_preaction}
