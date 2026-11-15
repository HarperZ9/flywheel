"""mcp_paths.py -- files inside a run's root that belong to the server, not the run.

The launch root confines an MCP run's file tools, and the server's own files can
sit inside it (the remote launch scripts start in the directory holding .env).
So an MCP run's file tools also refuse:

- the env file the remote entrypoint reads (RELAY_ENV_FILE, default ``.env``),
  for reads and writes: it holds the bearer token and the OAuth secrets;
- writes into the run store (RELAY_RUN_ROOT) and the session store
  (RELAY_SESSION_DIR or its per-user default), whose records a run could forge;
- writes into any ``.git`` directory, where a hook or a config line runs code
  the next time git runs in that tree;
- writes into agent and editor configuration (``.claude``, ``.codex``,
  ``.cursor``, ``.vscode``, ``.gemini``, ``.agents``, ``.opencode``, ``.mcp.json``),
  whose hooks, tasks and MCP servers run the next time a tool opens the tree.

On Windows a name that ends in a dot or a space, or that names a stream
(``a:b``), opens another spelling of a file, so a write to one is refused.

The limit: this covers the file tools only. With exec granted, a shell reaches
all of these, and a write elsewhere in the tree can still run later as code.
"""
from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from .local_tools import WRITE_TOOLS, ToolExecutor, ToolResult, _safe_path, edited_targets

NO_WRITE_NAMES = (".git",)
AGENT_CONFIG_NAMES = (".claude", ".codex", ".cursor", ".vscode", ".gemini", ".agents",
                      ".opencode", ".mcp.json")
_STORE_KEYS = ("RELAY_RUN_ROOT",)


def _canon(path: str) -> str:
    return os.path.normcase(os.path.realpath(path))


def _within(path: str, base: str) -> bool:
    return path == base or path.startswith(base.rstrip(os.sep) + os.sep)


@dataclass(frozen=True)
class ProtectedPaths:
    no_read: tuple[str, ...] = ()
    no_write: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {"no_read": list(self.no_read), "no_write": list(self.no_write),
                "no_write_names": [*NO_WRITE_NAMES, *AGENT_CONFIG_NAMES]}


def protected_paths(env: Mapping[str, str]) -> ProtectedPaths:
    """The server's own paths, resolved now against the server's working directory."""
    from .env_file import env_file_path
    from .session_store import session_dir
    env_file = _canon(env_file_path(env))
    stores = (*(_canon(env[k]) for k in _STORE_KEYS if env.get(k)), _canon(session_dir(env)))
    return ProtectedPaths(no_read=(env_file,), no_write=(env_file, *stores))


def _alias_name(rel: str) -> bool:
    """A Windows name that opens a file under another spelling."""
    _, tail = os.path.splitdrive(rel)
    parts = [p for p in re.split(r"[\\/]", tail) if p not in ("", ".", "..")]
    return any(p[-1] in ". " or ":" in p for p in parts)


def _write_refusal(root: str, rel: str, prot: ProtectedPaths, windows: bool) -> str | None:
    if windows and _alias_name(rel):
        return f"{rel!r} is another spelling of a file name on Windows"
    target = _safe_path(root, rel)
    if target is None:
        return None                      # the tool itself reports the escape
    inner = os.path.relpath(target, os.path.realpath(root))
    names = {p.lower() for p in re.split(r"[\\/]", inner)}
    if names & set(NO_WRITE_NAMES):
        return f"{rel!r} is inside a .git directory, where a write can run as code"
    if names & set(AGENT_CONFIG_NAMES):
        return f"{rel!r} is agent or editor configuration, which can run as code"
    if any(_within(os.path.normcase(target), p) for p in prot.no_write):
        return f"{rel!r} belongs to the relay server (env file, run or session store)"
    return None


def refusal(root: str, prot: ProtectedPaths, name: str, args: dict,
            *, windows: bool | None = None) -> str | None:
    """Why this call may not run, or None."""
    windows = os.name == "nt" if windows is None else windows
    if name in WRITE_TOOLS:
        for rel, _ in edited_targets(name, args):
            why = _write_refusal(root, rel, prot, windows)
            if why:
                return why
    path = args.get("path")
    if isinstance(path, str):
        if windows and _alias_name(path):
            return f"{path!r} is another spelling of a file name on Windows"
        target = _safe_path(root, path)
        if target is not None and os.path.normcase(target) in prot.no_read:
            return f"{path!r} is the relay server's env file, which holds its secrets"
    return None


@dataclass
class GuardedExecutor(ToolExecutor):
    """A ToolExecutor for MCP runs that also refuses the server's own paths."""
    protected: ProtectedPaths = field(default_factory=ProtectedPaths)

    def execute(self, name: str, args: dict) -> ToolResult:
        # The launch gate answers first, so a run without write still reads
        # "write disabled" rather than a reason about which file it named.
        why = None
        if isinstance(args, dict) and self.gate.check(name, args) is None:
            why = refusal(self.root, self.protected, name, args)
        if why:
            return ToolResult(name, args, False, f"[gate] {why}")
        return super().execute(name, args)
