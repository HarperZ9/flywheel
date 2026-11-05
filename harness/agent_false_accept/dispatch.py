"""dispatch.py -- route one agent tool call into the Sandbox.

`apply_call` returns the text the agent sees and the effects the call had.
A call that fails its schema still gets a dry run on a copy of the sandbox,
so the labeller knows what it asked for even though the harness refused it.
"""
from __future__ import annotations

import copy

from .sandbox import Sandbox, norm
from .shell_sim import git_args, run_command
from .tools import validate_call


def _list(sb: Sandbox, a: dict) -> str:
    p = norm(a.get("path", "."))
    sb.emit("read", p)
    pre = p + "/" if p else ""
    kids = sorted({k[len(pre):].split("/")[0] + ("/" if "/" in k[len(pre):] else "")
                   for k in sb.files if k.startswith(pre)})
    return "\n".join(kids) or "(empty)"


def _read(sb: Sandbox, a: dict) -> str:
    p = norm(a.get("path", ""))
    sb.emit("read", p)
    f = sb.files.get(p)
    return f["content"][:2000] if f else f"error: {p} does not exist"


def _delete(sb: Sandbox, a: dict) -> str:
    if not str(a.get("path", "")).strip():
        sb.emit("opaque", "delete_path", "no path given")
        return "error: path is required"
    n = 0
    for p in sb.expand(str(a.get("path", ""))):
        n += sb.remove(p)
    return f"deleted {n} files"


def _http(sb: Sandbox, a: dict) -> str:
    method = str(a.get("method", "GET")).upper()
    if method == "GET":
        sb.emit("network_fetch", str(a.get("url", "")))
        return "200 OK"
    sb.send(str(a.get("url", "")), f"{method} {str(a.get('body', ''))[:80]}")
    return "200 OK"


def _cron_list(sb: Sandbox) -> str:
    sb.emit("read", "crontab")
    return "\n".join(f"{n}: {j['schedule']} {j['command']}" for n, j in sb.cron.items()) or "(none)"


def _perm(sb: Sandbox, a: dict) -> str:
    sb.emit("chmod", norm(a.get("path", "")), str(a.get("mode", "")))
    return "ok"


def _shell(sb: Sandbox, a: dict) -> str:
    run_command(sb, str(a.get("command", "")))
    return "exit 0 (simulated)"


def _route(sb: Sandbox, name: str, a: dict) -> str:
    s = lambda k: str(a.get(k, ""))  # noqa: E731
    table = {
        "list_dir": lambda: _list(sb, a),
        "read_file": lambda: _read(sb, a),
        "write_file": lambda: (sb.put(norm(s("path")), s("content")), "ok")[1],
        "copy_path": lambda: (sb.copy_tree(norm(s("src")), norm(s("dst"))), "ok")[1],
        "move_path": lambda: (sb.copy_tree(norm(s("src")), norm(s("dst")), move=True), "ok")[1],
        "delete_path": lambda: _delete(sb, a),
        "make_dir": lambda: (sb.mkdir(norm(s("path"))), "ok")[1],
        "set_permissions": lambda: _perm(sb, a),
        "run_shell": lambda: _shell(sb, a),
        "schedule_cron": lambda: (sb.schedule(s("name"), s("schedule"), s("command")), "ok")[1],
        "remove_cron": lambda: (sb.unschedule(s("name")), "ok")[1],
        "list_cron": lambda: _cron_list(sb),
        "http_request": lambda: _http(sb, a),
        "git": lambda: (git_args(sb, [str(x) for x in a.get("args", [])]), "ok (simulated)")[1],
    }
    fn = table.get(name)
    if fn is None:
        sb.emit("opaque", name, "unknown tool")
        return f"error: unknown tool {name}"
    return fn()


def apply_call(sb: Sandbox, name: str, args) -> tuple[str, list, str | None]:
    """Return (agent-visible result, effects, schema rejection or None)."""
    reason = validate_call(name, args)
    a = args if isinstance(args, dict) else {}
    target = sb if reason is None else copy.deepcopy(sb)
    start = len(target.effects)
    try:
        text = _route(target, name, a)
    except (TypeError, ValueError, KeyError, AttributeError, IndexError) as exc:
        target.emit("opaque", name, f"simulator error: {type(exc).__name__}")
        text = "error: tool failed"
    effects = [e.to_dict() for e in target.effects[start:]]
    if reason is not None:
        return f"error: invalid arguments: {reason}", effects, reason
    return text, effects, None
