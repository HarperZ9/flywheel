"""`flywheel traces status` is a product surface: it states what each store's
deletion does in the pinned lane releases, and carries no package ids,
design section numbers, experiment ids or source file references. Those stay
in `--json` (the `package` field) and in the project docs."""
import re

from harness import trace_cli
from harness.trace_inventory_scan import resolve_roots, scan

INTERNAL = re.compile(r"\b(?:MN|CA|FW|EN|F|D|X)-?[A-Z]?\d+[a-z]?\b|\b\d\.\d+\b(?! ?[KMG]?i?B\b)|"
                      r"\.py:\d|closes in|experiment\b|#\d+|\w\.py\b|phase \d")


def _text(tmp_path, monkeypatch):
    home, run = tmp_path / "home", tmp_path / "run"
    home.mkdir()
    run.mkdir()
    monkeypatch.setenv("FLYWHEEL_HOME", str(home))
    monkeypatch.setenv("FLYWHEEL_RUN_ROOT", str(run))
    lines = trace_cli.render_status(scan(), resolve_roots())
    return "\n".join(lines[3:])  # after the home and run-root lines, which hold paths


def test_status_text_has_no_internal_references(tmp_path, monkeypatch):
    text = _text(tmp_path, monkeypatch)
    assert INTERNAL.findall(text) == []


def test_lane_deletion_is_stated_as_the_pinned_release_does_it(tmp_path, monkeypatch):
    text = _text(tmp_path, monkeypatch)
    assert "erases through its own forget" not in text
    assert "purges through its own context purge" not in text
    # mneme 0.5.1 erases source turns and derived rows; canon 0.4.2 purges from
    # its own command line, and Flywheel never calls it.
    assert "erases a memory with its source turns" in text
    assert "purges context records from its own command line" in text
    assert "Flywheel never calls purge" in text
    assert "raw turn" not in text and "canon has no deletion" not in text


def test_the_lane_copy_follows_the_pins_it_describes():
    """The deletion copy above describes these releases. A pin that moves fails
    here, so the copy is read again with the new release before this changes."""
    from harness.lanes_registry import LANES
    assert (LANES["mneme"].version, LANES["canon"].version) == ("0.5.1", "0.4.2")


def test_the_json_keeps_the_package_ids(tmp_path, monkeypatch):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path / "h"))
    monkeypatch.setenv("FLYWHEEL_RUN_ROOT", str(tmp_path / "r"))
    rows = {r["id"]: r for r in scan()["stores"]}
    assert rows["L1"]["operations"]["delete"]["package"] == "MN-01"
