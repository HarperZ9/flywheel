"""Shared setup for the Claude plugin tests.

The build, rules and smoke modules live in scripts/, outside the package, so
they are loaded here by path. PLUGIN_ENV and the server entry come from the
plugin's own .mcp.json, so the tests follow any change to what the plugin
declares.
"""
import importlib.util
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
TEMPLATE = ROOT / "claude-plugin"
SKILL = TEMPLATE / "skills" / "prose-review" / "SKILL.md"

_MCP = json.loads((TEMPLATE / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]
(SERVER_NAME, SERVER), = _MCP.items()
PLUGIN_ENV = dict(SERVER["env"])
PLUGIN_NAME = json.loads((TEMPLATE / ".claude-plugin" / "plugin.json")
                         .read_text(encoding="utf-8"))["name"]


def load(name):
    """Import scripts/<name>.py once and return the module."""
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


def callable_name(tool):
    """The name Claude Code gives a plugin tool: mcp__plugin_<plugin>_<server>__<tool>,
    with every character outside A-Z a-z 0-9 _ - replaced by an underscore."""
    return re.sub(r"[^A-Za-z0-9_-]", "_",
                  f"mcp__plugin_{PLUGIN_NAME}_{SERVER_NAME}__{tool}")
