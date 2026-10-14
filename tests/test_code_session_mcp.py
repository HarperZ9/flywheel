"""Falsifiers for MCP servers from config files in `flywheel code`."""
import json
import sys
import textwrap

from harness.code_session import cli, mcp_cli
from harness.code_session.backends import build_agent
from harness.code_session.mcp_config import ServerSpec, attach, load_specs, tool_prefix
from harness.code_session.session import new_session
from tests.test_code_session import ScriptBackend, _bare_runner

SERVER = textwrap.dedent('''
    import json, sys
    for line in sys.stdin:
        msg = json.loads(line)
        if "id" not in msg:
            continue
        m = msg["method"]
        if m == "initialize":
            res = {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}},
                   "serverInfo": {"name": "echo", "version": "1"}}
        elif m == "tools/list":
            res = {"tools": [{"name": "shout", "description": "upper-case a word",
                              "inputSchema": {"type": "object"}}]}
        elif m == "tools/call":
            res = {"content": [{"type": "text",
                                "text": msg["params"]["arguments"]["word"].upper()}]}
        else:
            res = {}
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": res}) + "\\n")
        sys.stdout.flush()
''')


def _write_server(tmp_path):
    script = tmp_path / "echo_server.py"
    script.write_text(SERVER, encoding="utf-8")
    return script


def _config(path, servers):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"mcpServers": servers}), encoding="utf-8")


def test_a_configured_server_is_started_and_its_tool_runs_through_the_loop(tmp_path):
    home = tmp_path / "home"
    script = _write_server(tmp_path)
    _config(home / "mcp.json", {"echo-srv": {"command": sys.executable, "args": [str(script)]}})
    specs, errors = load_specs(str(tmp_path), str(home))
    assert not errors and specs[0].trusted
    s = new_session(build_agent([ScriptBackend([
        'TOOL mcp__echo_srv__shout {"word": "heron"}', "It says HERON."])]),
        str(tmp_path), mode="auto", runner=_bare_runner)
    try:
        rows = attach(s, specs)
        assert rows[0]["status"] == "started"
        assert rows[0]["tools"] == ["mcp__echo_srv__shout"]
        s.turn("shout heron")
    finally:
        s.close()
    results = [e.content for e in s.ledger.entries if e.kind == "tool_result"]
    assert results == ["HERON"]
    assert any(e.kind == "mcp" for e in s.ledger.entries)


def test_project_servers_need_a_yes(tmp_path):
    _config(tmp_path / ".mcp.json", {"proj": {"command": "nonexistent-binary"}})
    specs, _ = load_specs(str(tmp_path), None)
    assert specs and not specs[0].trusted
    s = new_session(build_agent([ScriptBackend([])]), str(tmp_path), mode="auto")
    started = []
    rows = attach(s, specs, ask=None, connector=lambda spec: started.append(spec) or (None, {}))
    assert rows[0]["status"] == "skipped" and started == []
    rows = attach(s, specs, ask=lambda spec: True,
                  connector=lambda spec: (type("C", (), {"close": lambda self: None})(), {}))
    assert rows[0]["status"] == "started"


def test_a_failing_server_is_reported_not_fatal(tmp_path):
    s = new_session(build_agent([ScriptBackend([])]), str(tmp_path), mode="auto")
    spec = ServerSpec(name="bad", source="x", trusted=True, command=["no-such-program-xyz"])
    rows = attach(s, [spec])
    assert rows[0]["status"] == "failed" and rows[0]["reason"]


def test_mcp_tools_ask_in_ask_mode_and_are_refused_in_plan_mode(tmp_path):
    asked = []
    s = new_session(build_agent([ScriptBackend(['TOOL mcp__x__t {}', "ok"])]), str(tmp_path),
                    mode="ask", approver=lambda n, a: asked.append(n) or "no")
    s.executor.external["mcp__x__t"] = {"fn": lambda a: (True, "ran"), "description": "t"}
    s.turn("call it")
    assert asked == ["mcp__x__t"]
    p = new_session(build_agent([ScriptBackend(['TOOL mcp__x__t {}', "ok"])]), str(tmp_path),
                    mode="plan")
    calls = []
    p.executor.external["mcp__x__t"] = {"fn": lambda a: calls.append(a) or (True, "ran"),
                                        "description": "t"}
    p.turn("call it")
    assert calls == []


def test_config_shapes_and_errors(tmp_path):
    _config(tmp_path / ".flywheel" / "mcp.json", {
        "web": {"type": "http", "url": "https://example.org/mcp"},
        "empty": {}, "list": []})
    specs, errors = load_specs(str(tmp_path), None)
    assert [(s.name, s.url) for s in specs] == [("web", "https://example.org/mcp")]
    assert len(errors) == 2
    assert tool_prefix("my-server.v2") == "mcp__my_server_v2__"


def test_mcp_add_list_remove_round_trip(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(mcp_cli, "_home", lambda: str(tmp_path / "home"))
    monkeypatch.chdir(tmp_path)
    assert mcp_cli.main(["add", "files", "--", "npx", "-y", "fs-server"]) == 0
    assert mcp_cli.main(["add", "board", "--url", "https://example.org/mcp", "--project"]) == 0
    data = json.loads((tmp_path / "home" / "mcp.json").read_text(encoding="utf-8"))
    assert data["mcpServers"]["files"] == {"command": "npx", "args": ["-y", "fs-server"]}
    capsys.readouterr()
    assert mcp_cli.main(["list"]) == 0
    out = capsys.readouterr().out
    assert "files" in out and "board" in out and "asks before starting" in out
    assert mcp_cli.main(["remove", "files"]) == 0
    assert mcp_cli.main(["remove", "files"]) == 1


def test_print_mode_skips_project_servers_without_trust(tmp_path, monkeypatch, capsys):
    _config(tmp_path / ".mcp.json", {"proj": {"command": "should-not-start"}})
    monkeypatch.setattr(cli, "_home", lambda: str(tmp_path / "home"))
    monkeypatch.setattr(cli, "ladder", lambda **kw: [ScriptBackend(["done"])])
    assert cli.main(["-p", "x", "--root", str(tmp_path), "--no-save"]) == 0
    assert "proj: skipped" in capsys.readouterr().err


def test_mcp_is_a_packaged_command():
    from harness import cli_entry
    assert cli_entry._PACKAGED["mcp"] == "harness.code_session.mcp_cli"
