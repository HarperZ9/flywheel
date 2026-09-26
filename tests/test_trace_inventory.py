"""Custody inventory over a planted home: exact counts, and nothing unnamed.

I2 (no silent retention): every store that can hold trace-derived data is
registered, `flywheel traces status` lists each one with counts and bytes, and
an entry nobody registered shows up as UNREGISTERED instead of vanishing.
"""
import json
import tempfile

import pytest

from harness import trace_cli, trace_inventory, trace_inventory_scan

PLANT = b'{"planted": true}'
_ENV_KEYS = ("MNEME_STATE", "CANON_CONTEXT_DB", "FLYWHEEL_CANON_CONTEXT_DB",
             "RELAY_SESSION_DIR")


def _plant(store, home, run_root, tmp, env):
    """Write one file where `store` keeps its items."""
    name = store.patterns[0].replace("**/", "").replace("*", "x")
    if store.root == "env":
        target = tmp / "env" / store.id / name
        env[store.env[0]] = str(target)
    elif store.root == "client":
        env[store.env[0]] = str(tmp / "client" / store.id)
        target = tmp / "client" / store.id / name
    elif store.root == "temp":
        target = tmp / "temp" / name
    else:
        base = {"home": home, "state": home / "state", "run": run_root,
                "lanes": home / "lanes"}[store.root]
        target = base / name
    if store.shape == "dir" and store.root != "client":
        target = target / "item.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(PLANT)


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """No test reads the operator's real client history or temp directory."""
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "no-claude"))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "no-codex"))
    (tmp_path / "temp").mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "temp"))
    return tmp_path


@pytest.fixture
def planted(isolated, monkeypatch):
    home, run_root = isolated / "home", isolated / "run"
    home.mkdir(); run_root.mkdir()
    env = {"FLYWHEEL_HOME": str(home), "FLYWHEEL_RUN_ROOT": str(run_root)}
    for store in trace_inventory.stores():
        _plant(store, home, run_root, isolated, env)
    (home / "state" / "unexpected-store").mkdir(parents=True)
    (home / "state" / "unexpected-store" / "x.json").write_text("{}")
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return home, run_root, env


def test_planted_home_gives_exact_counts_and_one_unregistered(planted):
    _, _, env = planted
    doc = trace_inventory_scan.scan(environ=env)
    observed = {row["id"]: row["observed"] for row in doc["stores"]}
    assert set(observed) == {s.id for s in trace_inventory.stores()}
    wrong = {sid: o["files"] for sid, o in observed.items() if o["files"] != 1}
    assert wrong == {}
    assert all(o["bytes"] == len(PLANT) for o in observed.values())
    assert [(u["root"], u["name"]) for u in doc["unregistered"]] == [
        ("state", "unexpected-store")]


def test_status_prints_every_store_with_location_protection_and_gaps(planted, capsys):
    home, run_root, _ = planted
    assert trace_cli.main(["status"]) == 0
    out = capsys.readouterr().out
    for store in trace_inventory.stores():
        assert store.name in out
        assert trace_inventory_scan.location_text(store) in out
    assert "none (gap: FW-07b)" in out and "none (gap: FW-09)" in out
    assert "keep until you delete" in out
    assert "UNREGISTERED state/unexpected-store" in out
    assert "plaintext" in out
    absolute = [line for line in out.splitlines()
                if str(home) in line or str(run_root) in line]
    assert all(line.startswith(("home ", "run root ")) for line in absolute)


def test_status_json_validates_as_inventory_schema(planted, capsys):
    home, run_root, _ = planted
    assert trace_cli.main(["status", "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["schema"] == "flywheel.trace-inventory/v1"
    assert trace_inventory.validate_document(doc) == []
    text = json.dumps(doc)
    assert str(home) not in text and str(run_root) not in text
    broken = dict(doc, stores=[dict(doc["stores"][0], classes=["C9"])])
    assert trace_inventory.validate_document(broken) != []


def test_status_is_read_only_on_a_fresh_home(isolated, monkeypatch, capsys):
    home = isolated / "fresh"
    home.mkdir()
    monkeypatch.setenv("FLYWHEEL_HOME", str(home))
    monkeypatch.setenv("FLYWHEEL_RUN_ROOT", str(isolated / "run-missing"))
    assert trace_cli.main(["status"]) == 0
    assert list(home.iterdir()) == []
    assert not (isolated / "run-missing").exists()
    assert "0 files" in capsys.readouterr().out


def test_unclassified_stores_carry_a_note_and_show_in_status(planted, capsys):
    unclassified = [s for s in trace_inventory.stores() if s.classes is None]
    assert unclassified, "the inventory names what it cannot classify"
    assert all(s.note.strip() for s in unclassified)
    trace_cli.main(["status"])
    out = capsys.readouterr().out
    for store in unclassified:
        assert f"UNCLASSIFIED {store.id}" in out


def test_every_content_store_is_encrypted_or_a_named_exception():
    """I7's registry half: C1, C2, C3, C6 or C7 means encrypted or an exception
    that names its reason and the package or deferral that closes it."""
    content = {"C1", "C2", "C3", "C6", "C7"}
    for store in trace_inventory.stores():
        if store.root == "client":
            assert store.protection.kind == "outside-custody", store.id
            continue
        if store.classes is None or content & set(store.classes):
            p = store.protection
            assert p.kind in {"encrypted", "plaintext-exception"}, store.id
            if p.kind == "plaintext-exception":
                assert p.reason and p.package, store.id


def test_classify_matches_registered_exempt_and_unknown_names():
    assert trace_inventory.classify("state", "gateway-agent-traces").id == "S1"
    assert trace_inventory.classify("state", "native-cli-profile-ab12").id == "S6"
    exempt = trace_inventory.classify("home", "gateway.token")
    assert isinstance(exempt, trace_inventory.Exemption) and exempt.reason
    assert trace_inventory.classify("state", "never-heard-of-it") is None
