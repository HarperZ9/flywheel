"""relay.doctor says, per CLI tier, whether it can run and whether its isolation is proven.

A tier is PASS only when the CLI resolves to an absolute path, the launch grants
exec (and names the CLI when its profile is unproven), and the installed version
is the one the Q0 probes tested. Every other state is WARN with a setup code.
The doctor starts ``--version`` only when exec is granted, and never prints the
resolved path.
"""
import json

import pytest
from cli_stand_in import stand_in

import relay.local_mcp as m
from relay._vendor import safe_spawn
from relay.endpoints import PROVIDERS
from relay.mcp_grants import StartGrants


def _doctor():
    resp = m.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                     "params": {"name": "relay.doctor"}})
    return json.loads(resp["result"]["content"][0]["text"])


def _rows(body):
    return {r["tier"]: r for r in body["cli_tiers"]}


def _exec(monkeypatch):
    monkeypatch.setattr(m, "_GRANTS", StartGrants(root=m._GRANTS.root, allow_exec=True))


def test_without_exec_each_tier_warns_and_nothing_starts(world):
    record = str(world["tmp"] / "claude.json")
    stand_in(str(world["bin"]), "claude", record, version=safe_spawn.PROFILES["claude"].tested)
    rows = _rows(_doctor())
    assert rows["claude"]["status"] == "WARN" and rows["claude"]["setup"] == "EXEC_NOT_GRANTED"
    assert rows["claude"]["installed"] is True and rows["claude"]["profile_proven"] is True
    assert rows["codex"]["setup"] == "CLI_NOT_FOUND"
    assert not (world["tmp"] / "claude.json").exists()


def test_a_tested_version_under_exec_passes(world, monkeypatch):
    _exec(monkeypatch)
    for name in ("claude", "codex"):
        stand_in(str(world["bin"]), name, str(world["tmp"] / f"{name}.json"),
                 version=f"{name} {safe_spawn.PROFILES[name].tested} (stand-in)")
    rows = _rows(_doctor())
    for name in ("claude", "codex"):
        assert rows[name]["status"] == "PASS" and rows[name]["setup"] is None
        assert rows[name]["version"] == safe_spawn.PROFILES[name].tested
    assert str(world["bin"]) not in json.dumps(rows)


def test_an_untested_version_warns(world, monkeypatch):
    _exec(monkeypatch)
    stand_in(str(world["bin"]), "codex", str(world["tmp"] / "codex.json"), version="codex-cli 9.9.9")
    row = _rows(_doctor())["codex"]
    assert row["status"] == "WARN" and row["setup"] == "CLI_VERSION_UNTESTED"
    assert row["version"] == "9.9.9" and row["profile_tested"] == "0.144.6"


@pytest.fixture
def gemini_tier(world, monkeypatch):
    stand_in(str(world["bin"]), "gemini", str(world["tmp"] / "gemini.json"), version="1.0.0")
    spec = {**PROVIDERS["gemini"], "cli": {"argv": ["gemini"], "profile": "gemini",
                                           "override": "RELAY_GEMINI_CLI"}}
    monkeypatch.setitem(PROVIDERS, "gemini", spec)
    _exec(monkeypatch)


def test_an_unproven_profile_warns_until_a_grant_names_it(gemini_tier, monkeypatch):
    row = _rows(_doctor())["gemini"]
    assert row["status"] == "WARN" and row["setup"] == "CLI_PROFILE_UNPROVEN"
    assert row["profile_proven"] is False and row["named_grant"] is False
    monkeypatch.setenv("RELAY_ALLOW_EXEC_CLI", "gemini")
    row = _rows(_doctor())["gemini"]
    # Named, it can run, and the doctor still says its isolation is unproven.
    assert row["status"] == "WARN" and row["setup"] == "CLI_PROFILE_UNPROVEN"
    assert row["named_grant"] is True and row["usable"] is True


def test_the_existing_doctor_fields_are_kept(world):
    body = _doctor()
    assert body["ok"] is True and {"local_tiers", "tools", "remote", "grants"} <= set(body)
