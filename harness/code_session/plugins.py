"""plugins.py -- install bundles of commands, agents, skills, hooks and MCP servers.

A plugin is a folder in the shape Claude Code plugins use:

    plugin.json or .claude-plugin/plugin.json   {"name", "version", "description"}
    commands/*.md      slash commands          agents/*.md   subagents
    skills/*/SKILL.md  skills                  hooks/hooks.json  lifecycle hooks
    .mcp.json          MCP servers

`flywheel plugin install <folder or git URL>` copies it into
FLYWHEEL_HOME/code-plugins/<name>/ after showing what it contains (every hook
command and every MCP server command, since those run programs) and asking for
a yes (`--yes` skips the question). A git URL is cloned at its default branch
and the commit is recorded. `flywheel code` then loads installed plugins like
your own user-level files. `flywheel plugin list` and `flywheel plugin remove
NAME` manage them.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

FOLDER = "code-plugins"
REGISTRY = "code-plugins.json"
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class PluginError(RuntimeError):
    pass


def plugin_roots(home: "str | None") -> list:
    """Installed plugin folders, in name order."""
    if not home:
        return []
    base = Path(home) / FOLDER
    return sorted(p for p in base.iterdir() if p.is_dir()) if base.is_dir() else []


def manifest(folder: Path) -> dict:
    for candidate in (folder / ".claude-plugin" / "plugin.json", folder / "plugin.json"):
        if candidate.is_file():
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
            except ValueError as e:
                raise PluginError(f"{candidate} is not valid JSON") from e
            if isinstance(data, dict):
                return data
    return {"name": folder.name}


def summary(folder: Path) -> dict:
    """What a plugin would add, with every program it could start."""
    hooks, servers = [], []
    hook_file = folder / "hooks" / "hooks.json"
    if hook_file.is_file():
        from .hooks import _parse
        hooks = [f"{e.event}: {e.command}" for e in _parse(hook_file, [])]
    mcp_file = folder / ".mcp.json"
    if mcp_file.is_file():
        from .mcp_config import _parse as parse_mcp
        servers = [f"{s.name}: {s.url or ' '.join(s.command)}" for s in parse_mcp(mcp_file, True, [])]
    count = lambda pattern: len(list(folder.glob(pattern)))  # noqa: E731
    return {"commands": count("commands/*.md"), "agents": count("agents/*.md"),
            "skills": count("skills/*/SKILL.md"), "hooks": hooks, "mcp_servers": servers}


def _fetch(source: str, work: Path) -> "tuple[Path, str]":
    if re.match(r"^(https://|git@|file://)", source):
        from harness import safe_program
        argv, env = safe_program.launch(["git", "clone", "--depth", "1", source, str(work / "src")])
        p = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=300)
        if p.returncode != 0:
            raise PluginError(f"git clone failed: {(p.stderr or p.stdout).strip()[:300]}")
        argv, env = safe_program.launch(["git", "rev-parse", "HEAD"], cwd=str(work / "src"))
        commit = subprocess.run(argv, cwd=str(work / "src"), env=env, capture_output=True,
                                text=True, timeout=60).stdout.strip()
        return work / "src", f"{source}@{commit}"
    path = Path(source).expanduser().resolve()
    if not path.is_dir():
        raise PluginError(f"{source} is not a folder or a git URL")
    return path, str(path)


def install(source: str, home: str, *, confirm=None) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        folder, origin = _fetch(source, Path(tmp))
        name = str(manifest(folder).get("name") or folder.name)
        if not _NAME.match(name):
            raise PluginError(f"plugin name {name!r} is not a safe folder name")
        info = summary(folder)
        if confirm is not None and not confirm(name, info):
            raise PluginError("not installed")
        dest = Path(home) / FOLDER / name
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(folder, dest, ignore=shutil.ignore_patterns(".git"))
    record = {"name": name, "source": origin, "installed": time.time(), **info}
    _write_registry(home, {**_read_registry(home), name: record})
    return record


def remove(name: str, home: str) -> bool:
    dest = Path(home) / FOLDER / name
    if not _NAME.match(name) or not dest.is_dir():
        return False
    shutil.rmtree(dest)
    reg = _read_registry(home)
    reg.pop(name, None)
    _write_registry(home, reg)
    return True


def _read_registry(home: str) -> dict:
    path = Path(home) / REGISTRY
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except ValueError:
        return {}


def _write_registry(home: str, data: dict) -> None:
    path = Path(home) / REGISTRY
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def listing(home: str) -> str:
    reg = _read_registry(home)
    if not reg:
        return "no plugins installed"
    return "\n".join(f"{n:<20} {r.get('commands', 0)} command(s), {r.get('agents', 0)} agent(s), "
                     f"{r.get('skills', 0)} skill(s), {len(r.get('hooks', []))} hook(s), "
                     f"{len(r.get('mcp_servers', []))} MCP server(s)  from {r.get('source')}"
                     for n, r in sorted(reg.items()))
