"""The Train surface must not headline a stale 10-task partial when a
powered 110-task lane exists: the duel summary carries the uplift deltas
alongside, with the note steering readers to the stronger intervals."""

import json

from harness import train_surface


def test_duel_summary_carries_the_powered_lane(tmp_path, monkeypatch):
    duels = tmp_path / "artifacts" / "duels"
    duels.mkdir(parents=True)
    (duels / "old.partial.jsonl").write_text(
        "\n".join(json.dumps({"task_id": f"t{i}", "single": True,
                              "ext": True}) for i in range(4)),
        encoding="utf-8")
    uplift = tmp_path / "artifacts" / "uplift"
    uplift.mkdir(parents=True)
    (uplift / "run.json").write_text(json.dumps({
        "schema": "flywheel.uplift-bench/v1",
        "comparison_key": "uplift:hard_v2",
        "rows": [{"provider": "m", "arm": "bare"}],
        "deltas": [{"provider": "m", "uplift": 0.11,
                    "newcombe_95": [0.018, 0.201],
                    "includes_zero": False}],
    }), encoding="utf-8")
    monkeypatch.setattr(train_surface, "REPO", tmp_path)
    monkeypatch.setattr(train_surface, "_DUEL_DIR", duels)
    doc = train_surface.duel_summary()
    assert doc["status"] == "partial"
    assert doc["uplift"]["comparison_key"] == "uplift:hard_v2"
    assert doc["uplift"]["deltas"][0]["includes_zero"] is False
    assert "powered uplift lane" in doc["note"]


def test_without_uplift_artifacts_nothing_is_invented(tmp_path, monkeypatch):
    duels = tmp_path / "artifacts" / "duels"
    duels.mkdir(parents=True)
    (duels / "old.partial.jsonl").write_text(
        json.dumps({"task_id": "t0", "single": True, "ext": True}),
        encoding="utf-8")
    monkeypatch.setattr(train_surface, "REPO", tmp_path)
    monkeypatch.setattr(train_surface, "_DUEL_DIR", duels)
    doc = train_surface.duel_summary()
    assert "uplift" not in doc
