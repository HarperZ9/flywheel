"""Falsifiers for how each launcher reads the write and exec grants.

Load-bearing: (1) the grant variables parse strictly, and a typo stops the launch
instead of leaving a grant silently on or off; (2) flags and variables both
grant; (3) ``serve``, ``relay --mcp`` and the remote entrypoint configure the
grants they were launched with, and pin the launch root.
"""
import json
import os

import pytest

import relay.local_mcp as m
from relay.mcp_grants import StartGrants, grants_from_env, grants_from_launch


def _flags(grants):
    return grants.allow_write, grants.allow_exec


# --- (1) and (2) parsing ---

@pytest.mark.parametrize("raw,expected", [
    ("1", True), ("true", True), ("YES", True), ("on", True),
    ("", False), ("0", False), ("false", False), ("no", False), ("off", False),
])
def test_env_values_parse(raw, expected):
    assert grants_from_env({"RELAY_ALLOW_WRITE": raw}).allow_write is expected


def test_an_unrecognized_env_value_fails_closed_loudly():
    with pytest.raises(ValueError, match="RELAY_ALLOW_EXEC"):
        grants_from_env({"RELAY_ALLOW_EXEC": "maybe"})


def test_flags_or_environment_grant():
    assert grants_from_launch(allow_write=True, allow_exec=False, env={}) == \
        StartGrants(allow_write=True)
    assert grants_from_launch(allow_write=False, allow_exec=False,
                              env={"RELAY_ALLOW_EXEC": "1"}).allow_exec is True
    assert grants_from_launch(allow_write=False, allow_exec=False, env={}) == StartGrants()


# --- (3) launchers ---

def test_serve_takes_grants_from_its_launch(monkeypatch):
    import io

    monkeypatch.setattr(m, "_GRANTS", StartGrants())
    monkeypatch.delenv("RELAY_MCP_ROOT", raising=False)
    monkeypatch.setenv("RELAY_ALLOW_WRITE", "1")
    monkeypatch.delenv("RELAY_ALLOW_EXEC", raising=False)
    out = io.StringIO()
    m.serve(stdin=io.StringIO(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                          "params": {"name": "relay.status"}}) + "\n"),
            stdout=out)
    status = json.loads(json.loads(out.getvalue())["result"]["content"][0]["text"])
    assert status["grants"]["allow_write"] is True and status["grants"]["allow_exec"] is False
    assert status["grants"]["root"] == os.path.realpath(os.getcwd())

    m.serve(stdin=io.StringIO(""), stdout=io.StringIO(),
            grants=StartGrants(allow_exec=True))
    assert _flags(m._GRANTS) == (True, True)


def test_cli_mcp_passes_flag_grants_to_serve(monkeypatch):
    import sys
    import types

    from relay import local_agent_cli

    got = {}
    monkeypatch.delenv("RELAY_ALLOW_WRITE", raising=False)
    monkeypatch.delenv("RELAY_ALLOW_EXEC", raising=False)
    def fake_serve(grants=None):
        got["grants"] = grants
        return 0

    monkeypatch.setitem(sys.modules, "relay.local_mcp", types.SimpleNamespace(serve=fake_serve))
    monkeypatch.delenv("RELAY_MCP_ROOT", raising=False)
    assert local_agent_cli.main(["--mcp", "--allow-write"]) == 0
    assert got["grants"] == StartGrants(allow_write=True, root=os.path.realpath(os.getcwd()))


def test_cli_mcp_refuses_a_bad_env_value(monkeypatch, capsys):
    from relay import local_agent_cli

    monkeypatch.setenv("RELAY_ALLOW_WRITE", "sure")
    assert local_agent_cli.main(["--mcp"]) == 2
    assert "RELAY_ALLOW_WRITE" in capsys.readouterr().err


def test_remote_entrypoint_configures_the_launch_grants(monkeypatch):
    from relay import remote_cli

    class _Server:
        def serve_forever(self):
            raise KeyboardInterrupt

        def shutdown(self):
            pass

    monkeypatch.setattr(m, "_GRANTS", StartGrants())
    monkeypatch.setattr(remote_cli, "serve", lambda *a, **k: _Server())
    env = {"RELAY_REMOTE_TOKEN": "t", "RELAY_ALLOW_WRITE": "true"}
    monkeypatch.setattr(remote_cli, "resolved_env", lambda: (env, "none.env"))
    monkeypatch.setattr(remote_cli, "ignored_file_keys", lambda path: [])
    assert remote_cli.main() == 0
    assert _flags(m._GRANTS) == (True, False)
    assert m._GRANTS.root == os.path.realpath(os.getcwd())

    env["RELAY_ALLOW_EXEC"] = "perhaps"
    monkeypatch.setattr(m, "_GRANTS", StartGrants())
    assert remote_cli.main() == 2
    assert m._GRANTS == StartGrants()


def test_serve_stops_on_a_bad_value_instead_of_raising(monkeypatch, capsys):
    # Flywheel's bundled lane calls serve() with no grants; a typo there must
    # exit 2 with a message, the same as every other launcher.
    import io

    monkeypatch.setenv("RELAY_ALLOW_EXEC", "perhaps")
    assert m.serve(stdin=io.StringIO(""), stdout=io.StringIO()) == 2
    assert "RELAY_ALLOW_EXEC" in capsys.readouterr().err
    monkeypatch.delenv("RELAY_ALLOW_EXEC")
    monkeypatch.setenv("RELAY_MCP_ROOT", os.path.join(os.getcwd(), "no-such-dir-relay"))
    assert m.serve(stdin=io.StringIO(""), stdout=io.StringIO()) == 2
    assert "RELAY_MCP_ROOT" in capsys.readouterr().err
