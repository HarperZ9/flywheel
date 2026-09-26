"""I2, dynamic half: after real writers run, every top-level entry is known.

The drivers in `trace_inventory_drivers.py` call real Flywheel writers
(gateway agent run, scaffold with its snapshot store, memory notes,
operations and Journeys, grants, continuation, source context) against a
temporary FLYWHEEL_HOME and run root. Every top-level entry they leave under
the home, `state/`, the run root and `lanes/` must be registered or exempt.
Paths other processes write, and paths code the drivers do not reach builds,
stay outside this check; the static half and the stated limits cover them.
"""
import pytest

from harness import trace_inventory, trace_inventory_scan
import trace_inventory_drivers as drivers


@pytest.fixture
def swept(tmp_path, monkeypatch):
    home, run_root = tmp_path / "home", tmp_path / "run"
    home.mkdir(); run_root.mkdir()
    monkeypatch.setenv("FLYWHEEL_HOME", str(home))
    monkeypatch.setenv("FLYWHEEL_RUN_ROOT", str(run_root))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "no-claude"))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "no-codex"))
    failed = drivers.run_all(home, run_root)
    return home, run_root, failed


def test_every_representative_writer_ran(swept):
    assert swept[2] == {}


def test_every_top_level_entry_the_writers_left_is_registered_or_exempt(swept):
    home, run_root, _ = swept
    doc = trace_inventory_scan.scan(environ={"FLYWHEEL_HOME": str(home),
                                            "FLYWHEEL_RUN_ROOT": str(run_root)})
    assert doc["unregistered"] == []
    names = trace_inventory_scan.top_level_names(home, run_root)
    assert {("state", "gateway-agent-traces"), ("home", "store.db"),
            ("run", "snapshots"), ("run", "fold_index.json"),
            ("state", "gateway-operations"), ("state", "journeys"),
            ("state", "grants"), ("state", "continuation"),
            ("state", "source-context")} <= names
    for root, name in names:
        assert trace_inventory.classify(root, name) is not None, (root, name)


def test_the_sweep_flags_a_writer_that_leaves_an_unregistered_entry(swept):
    """False-success control: a new store nobody registered must fail it."""
    home, run_root, _ = swept
    (run_root / "a-new-unregistered-store").mkdir()
    doc = trace_inventory_scan.scan(environ={"FLYWHEEL_HOME": str(home),
                                            "FLYWHEEL_RUN_ROOT": str(run_root)})
    assert [(u["root"], u["name"]) for u in doc["unregistered"]] == [
        ("run", "a-new-unregistered-store")]


def test_stores_the_writers_filled_report_nonzero_counts(swept):
    home, run_root, _ = swept
    doc = trace_inventory_scan.scan(environ={"FLYWHEEL_HOME": str(home),
                                            "FLYWHEEL_RUN_ROOT": str(run_root)})
    counts = {row["id"]: row["observed"]["files"] for row in doc["stores"]}
    for store_id in ("S1", "S7", "S8", "S9", "S2", "S3", "S4", "S5"):
        assert counts[store_id] > 0, store_id
