"""normalize.py -- turn one proposed call into the facts the rules read.

Facts are: the kind of action (read, write, exec, mcp, web, delegate,
unknown), the shell command text if any, the paths the call names (made
absolute against the workspace, forward slashes, lower case), the network
hosts it names, and every string value in its arguments joined for text
rules. Pure: same call and context, same facts.
"""
from __future__ import annotations

import os
import re
import shlex
from dataclasses import dataclass, field

from .contract import ProposedCall, RunContext

_URL = re.compile(r"\b[a-z][a-z0-9+.-]*://([^/\s:'\"@]+@)?([^/\s:'\"]+)", re.IGNORECASE)
_SSH = re.compile(r"\b(?:ssh|scp|sftp|rsync)\b[^|;&\n]*?\b[\w.-]+@([\w.-]+)", re.IGNORECASE)
_PATCH_FILE = re.compile(r"^(?:\*\*\* (?:Update|Add|Delete) File:|\+\+\+ |--- )\s*(?:[ab]/)?(\S+)",
                         re.MULTILINE)
_PATH_KEYS = ("path", "file_path", "notebook_path", "target", "dest", "source")
_DELEGATE = re.compile(r"^(Task|Agent|spawn_agent)$|__(spawn|start)_?agent|_agent_(run|start)$")
_WEB = ("WebFetch", "WebSearch", "web_fetch", "web_search")
_WRITE_TOOLS = ("write_file", "edit_file", "apply_patch", "Write", "Edit", "MultiEdit",
                "NotebookEdit")


@dataclass
class Facts:
    kind: str
    command: str = ""
    paths: list = field(default_factory=list)
    hosts: list = field(default_factory=list)
    text: str = ""


def _strings(value, out: list) -> None:
    if isinstance(value, str):
        out.append(value)
    elif isinstance(value, dict):
        for v in value.values():
            _strings(v, out)
    elif isinstance(value, (list, tuple)):
        for v in value:
            _strings(v, out)


def norm_path(raw: str, workspace: str) -> str:
    p = raw.strip().strip("'\"").replace("\\", "/")
    if not p:
        return ""
    absolute = p.startswith(("/", "~")) or re.match(r"^[a-zA-Z]:/", p)
    if not absolute and workspace:
        while p.startswith("./"):
            p = p[2:]
        base = workspace.strip().strip("'\"").replace("\\", "/").rstrip("/")
        p = base + "/" + ("" if p == "." else p)
    # Home-fold last, after the path is absolute, so a workspace and a path
    # under the same home fold the same way (and the comparison holds).
    home = os.path.expanduser("~").replace("\\", "/")
    if home and p.lower().startswith(home.lower() + "/"):
        p = "~" + p[len(home):]
    return p.lower()


def _command(call: ProposedCall) -> str:
    args = call.args
    for key in ("cmd", "command"):
        value = args.get(key)
        if isinstance(value, list):
            return " ".join(str(v) for v in value)
        if isinstance(value, str):
            return value
    return ""


def _kind(call: ProposedCall, command: str) -> str:
    tool = call.tool
    if _DELEGATE.search(tool):
        return "delegate"
    if tool in _WEB:
        return "web"
    if tool == "apply_patch" or (tool in _WRITE_TOOLS):
        return "write"
    cap = call.capability_class()
    if cap == "builtin-exec" or command:
        return "exec"
    if cap == "builtin-read":
        return "read"
    if cap == "external-mcp":
        return "mcp"
    return "unknown"


def _split(command: str, posix: bool) -> list:
    try:
        return shlex.split(command, posix=posix)
    except ValueError:
        return command.split()


def _command_paths(command: str) -> list:
    """Paths a shell command names, read both ways. POSIX splitting matches
    bash, where a backslash escapes; cmd.exe and PowerShell (the executor's
    shell on Windows, and Codex's) keep it literal, so `del C:\\x\\y` names a
    path only under the non-POSIX reading. Taking both readings can add a
    path, never drop one, which is the safe direction for every path rule."""
    tokens = _split(command, True)
    if "\\" in command:
        tokens = tokens + [t for t in _split(command, False) if t not in tokens]
    out = []
    for tok in tokens:
        tok = tok.split("=", 1)[-1] if "=" in tok else tok
        tok = tok.lstrip("@<>")
        if "/" in tok or "\\" in tok or tok.startswith((".", "~")):
            if "://" not in tok:
                out.append(tok)
    return out


def extract(call: ProposedCall, ctx: RunContext) -> Facts:
    command = _command(call)
    kind = _kind(call, command)
    texts: list = []
    _strings(call.args, texts)
    text = "\n".join(texts)
    raw_paths = [call.args[k] for k in _PATH_KEYS if isinstance(call.args.get(k), str)]
    if call.tool == "apply_patch" or "*** Begin Patch" in text:
        raw_paths += [p for p in _PATCH_FILE.findall(text) if "/dev/null" not in p]
        if kind == "exec":
            kind = "write"
    elif command:
        raw_paths += _command_paths(command)
    paths = [p for p in (norm_path(r, ctx.workspace) for r in raw_paths) if p]
    hosts = sorted({m.group(2).lower() for m in _URL.finditer(text)}
                   | {m.lower() for m in _SSH.findall(command)})
    return Facts(kind=kind, command=command, paths=paths, hosts=hosts, text=text)
