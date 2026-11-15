"""Report the Articulate version on each local surface, and optionally align them.

Three surfaces can drift apart on one machine: the `articulate` command on PATH,
the MCP server that Claude Code starts from ~/.claude.json, and the Claude Code
plugin installed from a local marketplace folder. This script prints the version
each one runs and exits 1 when they disagree.

    python scripts/sync_local_install.py            # report only
    python scripts/sync_local_install.py --upgrade  # pip upgrade the PATH install first

The script never edits Claude Code settings. When the MCP server or the plugin
lags, it prints the step that fixes it.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

HOME = Path.home()


def run(cmd, env=None):
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=60, env=env)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"error: {exc}"
    return (out.stdout or out.stderr).strip()


def path_cli():
    exe = shutil.which("articulate")
    if not exe:
        return None, "not found"
    out = run([exe, "--version"])
    return exe, out[len("articulate "):] if out.startswith("articulate ") else "older than 0.14 (no --version)"


def mcp_server():
    try:
        servers = json.loads((HOME / ".claude.json").read_text(encoding="utf-8")).get("mcpServers", {})
    except (OSError, ValueError) as exc:
        return None, f"unreadable: {exc}"
    entry = servers.get("articulate")
    if not entry:
        return None, "not configured"
    env = None
    if entry.get("env", {}).get("PYTHONPATH"):
        import os
        env = {**os.environ, "PYTHONPATH": entry["env"]["PYTHONPATH"]}
    code = "import articulate;print(articulate.__version__)"
    return entry, run([entry["command"], "-c", code], env=env)


def plugin():
    try:
        rows = json.loads((HOME / ".claude/plugins/installed_plugins.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return f"unreadable: {exc}"
    for key, installs in rows.get("plugins", {}).items():
        if key.startswith("articulate-writing@"):
            return installs[0].get("version", "unknown")
    return "not installed"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--upgrade", action="store_true",
                    help="pip install --upgrade articulate-writing[mcp] for the PATH install")
    args = ap.parse_args(argv)
    if args.upgrade:
        print(run([sys.executable, "-m", "pip", "install", "-q", "--upgrade", "articulate-writing[mcp]"]))
    exe, cli = path_cli()
    entry, mcp = mcp_server()
    plug = plugin()
    print(f"PATH CLI    {cli}  ({exe})")
    print(f"MCP server  {mcp}  ({entry.get('command') if isinstance(entry, dict) else entry})")
    print(f"plugin      {plug}")
    if isinstance(entry, dict) and entry.get("env", {}).get("PYTHONPATH"):
        print("MCP server runs from a checkout through PYTHONPATH; point it at the installed package:")
        print("  claude mcp remove articulate -s user")
        print(f"  claude mcp add articulate -s user -- {sys.executable} -m articulate.mcp_server")
    if plug != cli:
        print("plugin lags; rebuild the marketplace folder, then:")
        print("  claude plugin marketplace update articulate-writing")
        print("  claude plugin update articulate-writing@articulate-writing")
    return 0 if len({cli, mcp, plug}) == 1 else 1


if __name__ == "__main__":
    sys.exit(main())
