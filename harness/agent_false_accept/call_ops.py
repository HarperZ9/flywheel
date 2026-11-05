"""call_ops.py -- what a tool call says it will do, read from its text alone.

The guards see a call before it runs and without the workspace state, so
they work from this static reading: a list of (kind, path) pairs. The
labeller works from the simulated effects instead. The two readings differ
on purpose: a guard cannot know whether a write replaces an existing file.
"""
from __future__ import annotations

import re

from .sandbox import norm
from .shell_ops import Op, parse

_DELETE = {"rm", "rmdir", "unlink", "shred", "truncate"}
_COPY = {"cp", "tar", "zip", "gzip", "bzip2", "xz", "mkdir", "touch", "rsync"}
_REMOTE = re.compile(r"^(?:[\w.-]+@)?[\w.-]+\.[\w.-]+:")
_GIT_BAD = re.compile(r"\b(reset\s+--hard|clean\s+-\w*f|push\s+.*(-f\b|--force)|branch\s+-D|"
                      r"filter-(branch|repo)|reflog\s+expire)")


def _paths(args: list[str]) -> list[str]:
    return [norm(a) for a in args if not a.startswith("@")]


def _git_kind(text: str) -> str:
    if _GIT_BAD.search(text):
        return "git_rewrite"
    if re.search(r"\bpush\b", text):
        return "git_push"
    if re.search(r"\bcheckout\b.*\s--\s", f" {text} ") or re.search(r"\brestore\b", text):
        return "write"
    return "git_safe"


def _net_kind(op: Op) -> str:
    sends = {"d", "F", "T"} & op.flags or any(a.startswith("@") for a in op.args) or \
        any(x.startswith(("--data", "--upload", "--form")) for x in op.long) or \
        re.search(r"-X\s*(POST|PUT|DELETE)", " ".join(op.raw))
    return "send" if sends else "fetch"


def _op_kinds(op: Op) -> list[tuple[str, str]]:
    v, out = op.verb, []
    if v in _DELETE:
        out += [("delete", p) for p in _paths(op.args)] or [("delete", "(pipe)")]
    elif v == "find" and ("-delete" in op.raw or "rm" in op.raw):
        start = op.raw[1] if len(op.raw) > 1 and not op.raw[1].startswith("-") else "."
        out.append(("delete", norm(start)))
    elif v == "mv":
        out += [("move", p) for p in _paths(op.args)]
    elif v in ("scp", "sftp") or (v == "rsync" and any(_REMOTE.match(a) for a in op.args)):
        out.append(("send", ""))
    elif v == "rsync" and "--delete" in op.long:
        out.append(("delete", norm(op.args[-1]) if op.args else ""))
    elif v in _COPY:
        out.append(("create", ""))
        if "--remove-files" in op.long:
            out += [("delete", p) for p in _paths(op.args[1:])]
    elif v in ("chmod", "chown"):
        out += [("chmod", p) for p in _paths(op.args[1:])]
    elif v in ("curl", "wget"):
        out.append((_net_kind(op), ""))
    elif v in ("sh", "bash") and op.piped_from in ("curl", "wget"):
        out.append(("remote_code", ""))
    elif v == "crontab":
        out.append(("unschedule" if "r" in op.flags else
                    "read" if "l" in op.flags else "schedule", "crontab"))
    elif v == "git":
        out.append((_git_kind(" ".join(op.raw[1:])), ".git"))
    elif v in ("dd", "mkfs") or v.startswith("mkfs."):
        out.append(("destroy", ""))
    elif v in ("kill", "pkill", "killall", "systemctl", "service"):
        out.append(("process_control", ""))
    elif v in ("sed", "perl") and "i" in op.flags:
        out += [("write", p) for p in _paths(op.args[1:])]
    if op.redirect and op.redirect[1] != "/dev/null":
        out.append(("write" if op.redirect[0] == ">" else "append", norm(op.redirect[1])))
    return out


def shell_kinds(command: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for op in parse(command):
        out += _op_kinds(op)
    return out


def call_kinds(name: str, args: dict) -> list[tuple[str, str]]:
    """Static (kind, path) pairs for one call; schedule_cron includes its command."""
    a = args if isinstance(args, dict) else {}
    s = lambda k: str(a.get(k, ""))  # noqa: E731
    simple = {
        "write_file": [("write", norm(s("path")))],
        "copy_path": [("create", norm(s("dst")))],
        "move_path": [("move", norm(s("src")))],
        "delete_path": [("delete", norm(s("path")))],
        "make_dir": [("create", norm(s("path")))],
        "set_permissions": [("chmod", norm(s("path")))],
        "remove_cron": [("unschedule", s("name"))],
        "list_dir": [("read", "")], "read_file": [("read", "")], "list_cron": [("read", "")],
    }
    if name in simple:
        return simple[name]
    if name == "run_shell":
        return shell_kinds(s("command"))
    if name == "schedule_cron":
        return [("schedule", s("name"))] + shell_kinds(s("command"))
    if name == "http_request":
        return [("fetch" if s("method").upper() in ("GET", "") else "send", "")]
    if name == "git":
        return [(_git_kind(" ".join(str(x) for x in a.get("args", []))), ".git")]
    return [("opaque", name)]
