"""The plugin folder alone, as a directory install receives it, starts its server and hook."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

from claude_plugin_helpers import ROOT, TEMPLATE, load

sync = load("sync_plugin_source")
rules = load("claude_plugin_rules")


def test_vendored_package_matches_src():
    problems = sync.drift()
    assert problems == [], ("claude-plugin/src/articulate differs from src/articulate; run "
                            "`python scripts/sync_plugin_source.py`: " + ", ".join(problems[:10]))


def test_a_drifted_copy_is_caught(tmp_path):
    target = tmp_path / "articulate"
    shutil.copytree(sync.TARGET, target)
    (target / "detector.py").write_text("# edited\n", encoding="utf-8")
    (target / "stale.py").write_text("x = 1\n", encoding="utf-8")
    assert {"detector.py", "stale.py"} <= set(sync.drift(target=target))


def _installed(tmp_path):
    folder = tmp_path / "installed" / "articulate-writing"
    shutil.copytree(TEMPLATE, folder, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    return folder


def _fill(folder, arg):
    return arg.replace("${CLAUDE_PLUGIN_ROOT}", folder.as_posix())


def _server(folder, cwd):
    entry = json.loads((folder / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]["articulate"]
    assert entry["command"] == "python3"
    requests = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                    "protocolVersion": "2025-06-18", "capabilities": {},
                    "clientInfo": {"name": "isolated-launch-test", "version": "1"}}},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}]
    env = {"PATH": "", "SYSTEMROOT": __import__("os").environ.get("SYSTEMROOT", ""), **entry["env"]}
    return subprocess.run([sys.executable] + [_fill(folder, a) for a in entry["args"]],
                          input="".join(json.dumps(r) + "\n" for r in requests),
                          capture_output=True, text=True, encoding="utf-8", timeout=120, cwd=cwd, env=env)


def _hook(folder, cwd, event):
    hook = json.loads((folder / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    command = hook["hooks"]["PostToolUse"][0]["hooks"][0]["command"]
    prefix = "python3 "
    assert command.startswith(prefix)
    args = [_fill(folder, a.strip('"')) for a in command[len(prefix):].split(" ")]
    return subprocess.run([sys.executable] + args, input=json.dumps(event), capture_output=True,
                          text=True, encoding="utf-8", timeout=60, cwd=cwd)


EDIT = {"hook_event_name": "PostToolUse", "tool_name": "Edit",
        "session_id": "s", "transcript_path": "/nonexistent/transcript.jsonl", "cwd": "/",
        "tool_input": {"file_path": "notes.md", "old_string": "We shipped 3 fixes on Monday.",
                       "new_string": "We shipped some fixes recently."}}


def test_plugin_folder_alone_starts_server_and_hook(tmp_path):
    folder = _installed(tmp_path)
    done = _server(folder, tmp_path)
    replies = [json.loads(line) for line in done.stdout.splitlines() if line.strip()]
    tools = [t["name"] for r in replies if r.get("id") == 2 for t in r["result"]["tools"]]
    assert {"check", "score", "edit_plan", "edit_submit"} <= set(tools), done.stderr
    hook = _hook(folder, tmp_path, EDIT)
    assert hook.returncode == 0 and "hookSpecificOutput" in hook.stdout, hook.stderr
    assert not list(folder.rglob("__pycache__"))
    shutil.rmtree(folder / "src")
    missing = _server(folder, tmp_path)
    assert missing.returncode == 1 and "bundled source is missing" in missing.stderr
    skipped = _hook(folder, tmp_path, EDIT)
    assert skipped.returncode == 0 and "bundled source is missing" in skipped.stderr


def test_plugin_folder_passes_the_bundle_rules():
    assert rules.check_files(TEMPLATE) == []


def test_the_plugin_carries_no_model_backend_or_key_reading_code():
    shipped = {p.name for p in sync.TARGET.glob("*.py")}
    assert not {"editing.py", "backends.py", "claude_cli.py"} & shipped
    for path in TEMPLATE.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for name in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "ARTICULATE_OPENAI_API_KEY"):
            assert name not in text, (path, name)


def test_a_hosted_tool_request_in_the_plugin_build_gets_a_plain_answer(tmp_path):
    folder = _installed(tmp_path)
    code = ("import sys, os; sys.path.insert(0, %r)\n"
            "os.environ.pop('ARTICULATE_MCP_TOOLS', None); os.environ.pop('ARTICULATE_LOCAL_ONLY', None)\n"
            "from articulate import mcp_server\n"
            "print(mcp_server.do_fix('A short draft.')['error'])\n" % str(folder / "src"))
    run = subprocess.run([sys.executable, "-I", "-S", "-B", "-c", code], capture_output=True,
                         text=True, timeout=60)
    assert run.returncode == 0, run.stderr
    assert "does not include" in run.stdout
