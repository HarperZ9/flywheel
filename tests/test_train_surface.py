"""The train surface must read duel evidence honestly: no artifacts -> a
named 'none', a partial -> labeled partial with the true rates, and the
harness lift is verified-minus-single, never inflated."""

import json

from harness import train_surface


def test_no_duel_reports_none(tmp_path, monkeypatch):
    monkeypatch.setattr(train_surface, "_DUEL_DIR", tmp_path / "empty")
    d = train_surface.duel_summary()
    assert d["status"] == "none"


def test_partial_is_labeled_and_lift_is_honest(tmp_path, monkeypatch):
    d = tmp_path / "duels"
    d.mkdir()
    rows = [
        {"task_id": "a", "single": True, "ext": True, "self": True, "cons": True},
        {"task_id": "b", "single": False, "ext": True, "self": True, "cons": False},
        {"task_id": "c", "single": True, "ext": True, "self": True, "cons": True},
        {"task_id": "d", "single": False, "ext": False, "self": False, "cons": False},
    ]
    (d / "run.partial.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    monkeypatch.setattr(train_surface, "_DUEL_DIR", d)
    s = train_surface.duel_summary()
    assert s["status"] == "partial"
    assert s["single_rate"] == 0.5   # a, c
    assert s["verified_rate"] == 0.75  # a, b, c
    assert s["harness_lift"] == 0.25
    assert s["rescued"] == ["b"]       # ext passed where single failed
    assert "PARTIAL" in s["note"]


def test_completed_artifact_preferred_over_partial(tmp_path, monkeypatch):
    d = tmp_path / "duels"
    d.mkdir()
    (d / "run.partial.jsonl").write_text(
        json.dumps({"task_id": "x", "single": False, "ext": False}),
        encoding="utf-8")
    (d / "run.json").write_text(json.dumps({"rows": [
        {"task_id": "x", "single": True, "ext": True}]}), encoding="utf-8")
    monkeypatch.setattr(train_surface, "_DUEL_DIR", d)
    s = train_surface.duel_summary()
    assert s["status"] == "complete"
    assert s["single_rate"] == 1.0
