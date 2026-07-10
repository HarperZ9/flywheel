"""gateway contract — the two SUPERAPP increment-2 falsifiers, unit-level.

Both verifiers must be able to fail:
  - a down local endpoint reads as unhealthy (not silently healthy)
  - touching a cataloged receipt moves the world root hash
Plus: enterprise providers expose credential-presence booleans, never values.
"""
import json

from harness import gateway


def test_world_root_hash_changes_when_a_receipt_changes(tmp_path):
    (tmp_path / "a.json").write_text('{"v": 1}', encoding="utf-8")
    catalog = ("a.json",)
    before = gateway.world_state(tmp_path, catalog)["root_hash"]
    (tmp_path / "a.json").write_text('{"v": 2}', encoding="utf-8")
    after = gateway.world_state(tmp_path, catalog)["root_hash"]
    assert before != after, "root hash did not move on a receipt change — catalog is fake"


def test_world_marks_missing_receipts_honestly(tmp_path):
    w = gateway.world_state(tmp_path, ("does_not_exist.json",))
    assert w["present_count"] == 0
    assert w["receipts"][0]["sha256"] == "MISSING"
    assert w["receipts"][0]["present"] is False


def test_world_root_hash_stable_when_nothing_changes(tmp_path):
    (tmp_path / "a.json").write_text("stable", encoding="utf-8")
    h1 = gateway.world_state(tmp_path, ("a.json",))["root_hash"]
    h2 = gateway.world_state(tmp_path, ("a.json",))["root_hash"]
    assert h1 == h2


def test_down_local_endpoint_reads_unhealthy():
    # ports chosen to be almost certainly closed -> probe must fail closed
    roster = gateway.endpoint_roster("http://127.0.0.1:9", "http://127.0.0.1:9")
    assert roster["local_healthy"] == 0
    assert all(e["healthy"] is False for e in roster["local"])


def test_enterprise_reports_credential_presence_not_values(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fake-canary-value")
    roster = gateway.endpoint_roster("http://127.0.0.1:9", "http://127.0.0.1:9")
    blob = json.dumps(roster)
    assert "sk-fake-canary-value" not in blob, "a key VALUE leaked into the roster"
    codex = next((e for e in roster["enterprise"] if e["name"] == "codex"), None)
    if codex is not None:  # roster present only if endpoints.py imported
        assert codex["credential_present"] is True
        assert codex["key_env"] == "OPENAI_API_KEY"


def test_spine_roster_present():
    w = gateway.world_state(gateway.REPO)
    assert "local-model" in w["spine"] and "telos" in w["spine"]
