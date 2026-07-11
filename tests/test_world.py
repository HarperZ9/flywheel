"""Falsifier for the projected world (harness/world.py).

The load-bearing property: the world is re-derivable and its root hash MOVES when
any composed part (roster, findings, cursor) changes -- the world snapshot is
itself a receipt, and verify_world() can fail.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.world import project_world, verify_world, MATCH, DRIFT, UNVERIFIABLE


def _state(repo: Path, text: str):
    (repo / "STATE.md").write_text(text, encoding="utf-8")


def test_world_has_all_parts(tmp_path):
    _state(tmp_path, "# STATE\nLast updated: 2026-07-11\n\n## now\n")
    w = project_world(run_root=tmp_path, repo_root=tmp_path)
    assert w["schema"] == "flywheel.projected-world/v1"
    assert "root_hash" in w and w["root_hash"]
    for part in ("roster", "spine", "findings", "cursor"):
        assert part in w


def test_verify_match_on_fresh(tmp_path):
    _state(tmp_path, "# STATE\nLast updated: 2026-07-11\n\n## now\n")
    w = project_world(run_root=tmp_path, repo_root=tmp_path)
    assert verify_world(w, run_root=tmp_path, repo_root=tmp_path) == MATCH


def test_drift_when_cursor_moves(tmp_path):
    _state(tmp_path, "# STATE\nLast updated: 2026-07-11\n\n## now\n")
    w = project_world(run_root=tmp_path, repo_root=tmp_path)
    _state(tmp_path, "# STATE\nLast updated: 2026-07-12\n\n## later\n")   # cursor moved
    assert verify_world(w, run_root=tmp_path, repo_root=tmp_path) == DRIFT


def test_drift_when_a_receipt_appears(tmp_path):
    _state(tmp_path, "# STATE\nLast updated: 2026-07-11\n\n## now\n")
    w = project_world(run_root=tmp_path, repo_root=tmp_path)
    import json
    (tmp_path / "difficulty_screen_hard_v2_110.json").write_text(
        json.dumps({"n_tasks": 110, "headroom_at_temp0": ["t"] * 61}), encoding="utf-8")
    assert verify_world(w, run_root=tmp_path, repo_root=tmp_path) == DRIFT   # findings moved


def test_root_hash_stable_when_unchanged(tmp_path):
    _state(tmp_path, "# STATE\nLast updated: 2026-07-11\n\n## now\n")
    a = project_world(run_root=tmp_path, repo_root=tmp_path)["root_hash"]
    b = project_world(run_root=tmp_path, repo_root=tmp_path)["root_hash"]
    assert a == b


def test_unverifiable_without_root_hash(tmp_path):
    assert verify_world({}, run_root=tmp_path, repo_root=tmp_path) == UNVERIFIABLE
    assert verify_world({"schema": "x"}, run_root=tmp_path, repo_root=tmp_path) == UNVERIFIABLE


def test_missing_state_is_honest(tmp_path):
    w = project_world(run_root=tmp_path, repo_root=tmp_path)     # no STATE.md
    assert w["cursor"]["present"] is False
