"""Falsifiers for the launch root, the path half of the launch grants.

Load-bearing: (1) a run's ``root`` argument only narrows the root the server was
launched with, so a root outside it, reached by an absolute path, ``..`` or a
link, is refused with ROOT_NOT_GRANTED before the agent runs; (2) a relative
root resolves under the launch root, not the process's working directory;
(3) every launcher pins the root: ``relay --mcp --root``,
``python -m relay.local_mcp --root`` and RELAY_MCP_ROOT, defaulting to the
working directory; (4) ``python -m relay.local_mcp`` parses its flags and
refuses one it does not know instead of ignoring it.
"""
import json
import os

import pytest

import relay.local_mcp as m
from relay.mcp_grants import StartGrants, grants_from_env, grants_from_launch, pin_root


class _Stub:
    name = "stub"

    def health(self):
        return True

    def chat(self, messages, *, system, max_tokens, temperature, seed):
        return {"text": "done", "model_ref": "stub:root", "seed": seed}


@pytest.fixture
def work(monkeypatch, tmp_path):
    """A server launched over tmp_path/work with the write grant."""
    root = tmp_path / "work"
    (root / "sub").mkdir(parents=True)
    (tmp_path / "elsewhere").mkdir()
    monkeypatch.setattr(m, "_GRANTS", StartGrants(allow_write=True, root=str(root)))
    return root


@pytest.fixture
def seen(monkeypatch):
    record = {}

    def fake_run_agent(agent, goal, ex, ledger, **kwargs):
        record["root"] = ex.root
        return {"final": "done", "steps": 1, "verified": True, "final_answer": True,
                "chain_ok": True, "checkpoint": "c0", "accepted": True,
                "check_passed": None, "ledger": ledger}

    monkeypatch.setattr(m, "available_backends", lambda *, model="": [_Stub()])
    monkeypatch.setattr(m, "run_agent", fake_run_agent)
    return record


def _call(name, args):
    resp = m.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                     "params": {"name": name, "arguments": args}})
    return resp["result"]


def _body(res):
    return json.loads(res["content"][0]["text"])


# --- (1) the root argument only narrows ---

@pytest.mark.parametrize("tool", ["local_agent_run", "local_agent_start"])
def test_a_root_outside_the_launch_root_is_refused(work, seen, tool):
    for root in (str(work.parent / "elsewhere"), "../elsewhere", "sub/../..", "/"):
        res = _call(tool, {"goal": "plant", "root": root, "allow_write": True})
        assert res.get("isError") is True
        body = _body(res)
        assert body["error"]["code"] == "ROOT_NOT_GRANTED"
        assert body["request_binding"]["granted_root"] == os.path.realpath(work)
    assert seen == {}


def test_a_link_out_of_the_launch_root_is_refused(work, seen):
    link = work / "out"
    try:
        os.symlink(work.parent / "elsewhere", link, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("this platform or account cannot create a directory link")
    res = _call("local_agent_run", {"goal": "plant", "root": "out"})
    assert _body(res)["error"]["code"] == "ROOT_NOT_GRANTED"
    assert seen == {}


def test_a_prefix_sibling_is_not_inside(work, seen):
    # work2 starts with the same characters as work and is not under it.
    (work.parent / "work2").mkdir()
    res = _call("local_agent_run", {"goal": "g", "root": str(work.parent / "work2")})
    assert _body(res)["error"]["code"] == "ROOT_NOT_GRANTED"


# --- (2) a relative root resolves under the launch root ---

def test_roots_resolve_under_the_launch_root(work, seen):
    body = _body(_call("local_agent_run", {"goal": "g", "root": "sub"}))
    assert seen["root"] == os.path.realpath(work / "sub")
    assert body["request_binding"]["root"] == os.path.realpath(work / "sub")
    assert body["request_binding"]["requested_root"] == "sub"
    assert body["request_binding"]["granted_root"] == os.path.realpath(work)

    body = _body(_call("local_agent_run", {"goal": "g"}))
    assert seen["root"] == os.path.realpath(work)
    assert body["request_binding"]["requested_root"] is None

    _call("local_agent_run", {"goal": "g", "root": str(work / "sub")})
    assert seen["root"] == os.path.realpath(work / "sub")


def test_status_reports_the_launch_root(work):
    grants = _body(_call("relay.status", {}))["grants"]
    assert grants["root"] == os.path.realpath(work)
    assert grants["allow_write"] is True


# --- (3) the launchers pin the root ---

def test_pin_root_resolves_and_refuses_a_missing_directory(tmp_path, monkeypatch):
    assert pin_root(StartGrants(root=str(tmp_path))).root == os.path.realpath(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert pin_root(StartGrants()).root == os.path.realpath(tmp_path)
    with pytest.raises(ValueError, match="RELAY_MCP_ROOT|root"):
        pin_root(StartGrants(root=str(tmp_path / "missing")))


def test_configure_pins_the_root(monkeypatch, tmp_path):
    m.configure(StartGrants(allow_write=True, root=str(tmp_path)))
    assert m._GRANTS.root == os.path.realpath(tmp_path)
    assert m._GRANTS.allow_write is True


def test_root_from_env_and_flag():
    assert grants_from_env({"RELAY_MCP_ROOT": "/w"}).root == "/w"
    assert grants_from_env({}).root is None
    got = grants_from_launch(allow_write=False, allow_exec=False, root="/flag",
                             env={"RELAY_MCP_ROOT": "/w"})
    assert got.root == "/flag"
    assert grants_from_launch(allow_write=False, allow_exec=False, root=None,
                              env={"RELAY_MCP_ROOT": "/w"}).root == "/w"


def test_cli_mcp_passes_root_to_serve(monkeypatch, tmp_path):
    import sys
    import types

    from relay import local_agent_cli

    got = {}
    for key in ("RELAY_ALLOW_WRITE", "RELAY_ALLOW_EXEC", "RELAY_MCP_ROOT"):
        monkeypatch.delenv(key, raising=False)

    def fake_serve(grants=None):
        got["grants"] = grants
        return 0

    monkeypatch.setitem(sys.modules, "relay.local_mcp", types.SimpleNamespace(serve=fake_serve))
    assert local_agent_cli.main(["--mcp", "--root", str(tmp_path)]) == 0
    assert got["grants"].root == os.path.realpath(tmp_path)
    assert local_agent_cli.main(["--mcp"]) == 0
    assert got["grants"].root == os.path.realpath(os.getcwd())
    assert local_agent_cli.main(["--mcp", "--root", str(tmp_path / "missing")]) == 2


# --- (4) the module entrypoint parses its flags ---

def test_module_main_takes_flags(monkeypatch, tmp_path):
    got = {}
    for key in ("RELAY_ALLOW_WRITE", "RELAY_ALLOW_EXEC", "RELAY_MCP_ROOT"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(m, "serve", lambda grants=None, **k: got.setdefault("g", grants) and 0)
    m.main(["--allow-write", "--root", str(tmp_path)])
    assert got["g"].allow_write is True and got["g"].allow_exec is False
    assert got["g"].root == os.path.realpath(tmp_path)


def test_module_main_refuses_an_unknown_flag(monkeypatch, capsys):
    monkeypatch.setattr(m, "serve", lambda **k: pytest.fail("served with a bad flag"))
    with pytest.raises(SystemExit) as exc:
        m.main(["--allow-wrte"])
    assert exc.value.code == 2
