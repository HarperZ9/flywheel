"""The marketplace must be a catalog, not a side door: installing only
registers a launch command, credentials appear as env var names only, the
installed flag reflects the real registry, and a broken user catalog never
hides the builtin one."""

import json

from harness import marketplace, plugins


def _isolate(monkeypatch, tmp_path):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))


def test_catalog_shape_and_credential_names_only(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    doc = marketplace.marketplace_catalog()
    assert doc["schema"] == "flywheel.marketplace/v1"
    names = {e["name"] for e in doc["entries"]}
    assert {"filesystem", "fetch", "github", "playwright"} <= names
    gh = next(e for e in doc["entries"] if e["name"] == "github")
    assert gh["requires"] == ["GITHUB_PERSONAL_ACCESS_TOKEN"]
    assert "GITHUB_PERSONAL_ACCESS_TOKEN" in gh["credential_note"]
    assert "nothing downloads or runs" in doc["note"]


def test_install_registers_and_flags_installed(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    out = marketplace.install_from_catalog("fetch")
    assert out.get("registered") == "fetch"
    doc = marketplace.marketplace_catalog()
    fetch = next(e for e in doc["entries"] if e["name"] == "fetch")
    assert fetch["installed"] is True
    # And it is a real registry entry, probe-able and removable.
    roster = plugins.plugin_roster()
    assert any(p["name"] == "fetch" and p["kind"] == "mcp"
               for p in roster["plugins"])


def test_unknown_entry_is_a_named_error(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    assert "error" in marketplace.install_from_catalog("nonexistent")


def test_user_catalog_merges_and_broken_file_degrades(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    (tmp_path / "catalog.json").write_text(json.dumps({
        "entries": [{"name": "mine", "command": ["mytool", "mcp"]}]}),
        encoding="utf-8")
    names = {e["name"] for e in marketplace.marketplace_catalog()["entries"]}
    assert "mine" in names and "filesystem" in names
    # Broken user catalog: builtin entries still present.
    (tmp_path / "catalog.json").write_text("{not json", encoding="utf-8")
    names = {e["name"] for e in marketplace.marketplace_catalog()["entries"]}
    assert "filesystem" in names and "mine" not in names
