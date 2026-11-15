"""The claude and codex CLI tiers start isolated, through the vendored safe_spawn.

Falsifiers for the 0.3.0 audit finding B (P4, the Articulate class): the tiers
started the CLI by bare name from the server's folder with every variable, the
prompt on argv, and no isolation flags. Each test runs a real process, a
stand-in named like the CLI (``cli_stand_in``). No model is reached. The real
CLI's behavior under the profile is proven by the Q0 isolation probes.
"""
import json
import os

import pytest
from cli_stand_in import FAKE_KEY, WINDOWS, plant_binary, stand_in

import relay.local_mcp as m
from relay._vendor import safe_spawn
from relay.endpoints import PROVIDERS, BackendError, CliBackend, build_endpoints
from relay.mcp_grants import StartGrants

_MSG = [{"role": "user", "content": "hi"}]
CLAUDE_PROFILE = ["--setting-sources", "user", "--strict-mcp-config", "--tools", ""]


def _tier(provider):
    (b,) = build_endpoints(providers=[provider], modes=("plan",), only_configured=False)
    return b


def _seen(record):
    with open(record, encoding="utf-8") as fh:
        return json.load(fh)


def test_a_planted_claude_exe_loses_to_the_resolved_one(world):
    record = str(world["tmp"] / "claude.json")
    stand_in(str(world["bin"]), "claude", record)
    planted_marker = world["tmp"] / "PLANTED-RAN"
    plant_binary(str(world["project"]), "claude", str(planted_marker))
    out = _tier("claude").chat(_MSG, system="", max_tokens=8, temperature=0, seed=0)
    assert out["text"] == "STUB-ANSWER" and not planted_marker.exists()


def test_a_planted_project_settings_hook_leaves_no_marker(world):
    record = str(world["tmp"] / "claude.json")
    stand_in(str(world["bin"]), "claude", record)
    _tier("claude").chat(_MSG, system="", max_tokens=8, temperature=0, seed=0)
    seen = _seen(record)
    assert not world["marker"].exists()
    assert seen["listing"] == []
    assert os.path.normcase(seen["cwd"]) != os.path.normcase(str(world["project"]))
    assert seen["args"][-len(CLAUDE_PROFILE):] == CLAUDE_PROFILE


def test_the_cli_child_never_sees_a_provider_key(world):
    record = str(world["tmp"] / "claude.json")
    stand_in(str(world["bin"]), "claude", record)
    _tier("claude").chat(_MSG, system="", max_tokens=8, temperature=0, seed=0)
    env = _seen(record)["env"]
    assert FAKE_KEY not in json.dumps(env)
    if WINDOWS:
        assert {k.upper(): v for k, v in env.items()}["NODEFAULTCURRENTDIRECTORYINEXEPATH"] == "1"


def test_ampersand_and_paren_reach_the_stand_in_unchanged_on_stdin(world):
    record = str(world["tmp"] / "claude.json")
    stand_in(str(world["bin"]), "claude", record)
    text = 'print("a & b") ) | c ^ "d" %PATH% !x!'
    msgs = [{"role": "user", "content": text}]
    _tier("claude").chat(msgs, system="", max_tokens=8, temperature=0, seed=0)
    seen = _seen(record)
    assert text in seen["stdin"]
    assert not any(text in a for a in seen["args"]), "the prompt went on argv"


def test_the_codex_tier_answers_through_its_shim_with_the_proven_profile(world):
    record = str(world["tmp"] / "codex.json")
    stand_in(str(world["bin"]), "codex", record)
    out = _tier("codex").chat(_MSG, system="sys", max_tokens=8, temperature=0, seed=0)
    seen = _seen(record)
    profile = list(safe_spawn.PROFILES["codex"].before)
    assert out["text"] == "STUB-ANSWER"
    assert seen["args"] == profile + ["-"] and "user: hi" in seen["stdin"]
    assert seen["listing"] == [] and FAKE_KEY not in json.dumps(seen["env"])


def test_the_override_must_be_absolute(world, monkeypatch):
    record = str(world["tmp"] / "claude.json")
    real = stand_in(str(world["bin"]), "claude", record)
    monkeypatch.setenv("RELAY_CLAUDE_CLI", os.path.basename(real))
    tier = _tier("claude")
    assert tier.health() is False
    with pytest.raises(BackendError, match="BAD_OVERRIDE"):
        tier.chat(_MSG, system="", max_tokens=8, temperature=0, seed=0)
    monkeypatch.setenv("RELAY_CLAUDE_CLI", real)
    assert _tier("claude").chat(_MSG, system="", max_tokens=8, temperature=0,
                                seed=0)["text"] == "STUB-ANSWER"


def test_a_named_child_variable_reaches_the_cli(world, monkeypatch):
    record = str(world["tmp"] / "claude.json")
    stand_in(str(world["bin"]), "claude", record)
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.invalid:3128")
    monkeypatch.setenv("RELAY_CHILD_ENV", "HTTPS_PROXY")
    _tier("claude").chat(_MSG, system="", max_tokens=8, temperature=0, seed=0)
    env = {k.upper(): v for k, v in _seen(record)["env"].items()}
    assert env["HTTPS_PROXY"] == "http://proxy.invalid:3128" and FAKE_KEY not in json.dumps(env)


def test_a_failing_cli_is_a_backend_error(world):
    bad = CliBackend("x-plan", ["definitely-not-installed-cli"], profile="claude")
    assert bad.health() is False
    with pytest.raises(BackendError, match="NOT_FOUND"):
        bad.chat(_MSG, system="", max_tokens=8, temperature=0, seed=0)


# --- tiers whose isolation profile Q0 has not proven ---

@pytest.fixture
def unproven(world, monkeypatch):
    """A gemini CLI tier. Relay ships none today; this pins the rule for one."""
    record = str(world["tmp"] / "gemini.json")
    stand_in(str(world["bin"]), "gemini", record)
    spec = {**PROVIDERS["gemini"], "cli": {"argv": ["gemini"], "profile": "gemini",
                                           "override": "RELAY_GEMINI_CLI"}}
    monkeypatch.setitem(PROVIDERS, "gemini", spec)
    monkeypatch.setattr(m, "available_backends", lambda *, model="": [])
    monkeypatch.setattr(m, "_GRANTS", StartGrants(root=m._GRANTS.root, allow_exec=True))
    return record


def _chat(backend):
    resp = m.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
        "name": "local_agent_chat",
        "arguments": {"prompt": "hi", "online": True, "backend": backend}}})
    return resp["result"], json.loads(resp["result"]["content"][0]["text"])


def test_an_unproven_tier_is_refused_under_exec_without_a_grant_naming_it(unproven):
    result, body = _chat("gemini-plan")
    assert result.get("isError") is True and body["error"]["code"] == "EXEC_NOT_GRANTED"
    assert "RELAY_ALLOW_EXEC_CLI" in body["error"]["message"]
    assert not os.path.exists(unproven)
    assert "gemini-plan" not in {b.name for b in build_endpoints(modes=("plan",))}
    with pytest.raises(BackendError, match="GRANT_REQUIRED"):
        _tier("gemini").chat(_MSG, system="", max_tokens=8, temperature=0, seed=0)


def test_a_grant_naming_the_unproven_tier_opens_it(unproven, monkeypatch):
    monkeypatch.setenv("RELAY_ALLOW_EXEC_CLI", "gemini")
    result, body = _chat("gemini-plan")
    assert result.get("isError") is not True and body["text"] == "STUB-ANSWER"


def test_the_named_grant_does_not_stand_in_for_exec(unproven, monkeypatch):
    monkeypatch.setenv("RELAY_ALLOW_EXEC_CLI", "gemini")
    monkeypatch.setattr(m, "_GRANTS", StartGrants(root=m._GRANTS.root))
    result, body = _chat("gemini-plan")
    assert body["error"]["code"] == "EXEC_NOT_GRANTED" and not os.path.exists(unproven)
