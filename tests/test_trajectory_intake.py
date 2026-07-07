"""Falsifiers for trajectory_intake.py — the consumer side of the forum bridge.

Load-bearing: (1) the PINNED cross-side vector — a frozen forum-exported row
re-derives to a known merkle root with local stdlib only (no forum import); if
either side's hash recipe drifts, this fails loudly; (2) tampering an entry
DRIFTs the witness; (3) flipping a recorded grade input changes the re-derived
reward and fails closed; (4) the mapped row feeds the UNCHANGED data_flywheel;
(5) a broken seal is refused on load.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from harness import data_flywheel
from harness.trajectory_intake import (
    load_forum_jsonl,
    recheck_witness,
    to_gradable_row,
)

_FIXTURE = Path(__file__).parent / "fixtures_forum_gradable_pinned.json"
PINNED_MERKLE_ROOT = "b79c96da02ece2a7ce60f75ff9611c7acfa30ea4d028015604e438bf7cfda1dc"


def _row():
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


def test_pinned_witness_vector_matches_forum():
    # the frozen forum-exported row re-derives to MATCH with local stdlib only,
    # and the merkle root reproduces the constant forum's own test pins.
    v = recheck_witness(_row())
    assert v["witness"] == "MATCH", v["reasons"]
    assert v["root_reproduced"] == PINNED_MERKLE_ROOT
    assert v["reward_reproduced"] == 1.0


def test_tampered_entry_field_drifts():
    row = _row()
    row["trajectory"]["entries"][2]["actor"] = "impostor"  # tamper a field
    v = recheck_witness(row)
    assert v["witness"] == "DRIFT"
    assert any("tampered" in r or "chain" in r or "merkle" in r for r in v["reasons"])


def test_tampered_entry_hash_drifts():
    row = _row()
    row["trajectory"]["entries"][3]["entry_hash"] = "0" * 64  # tamper the shipped hash
    v = recheck_witness(row)
    assert v["witness"] == "DRIFT"


def test_flipped_grade_input_changes_reward():
    row = _row()
    row["oracle"]["grade_inputs"][0]["ok"] = False  # flip a passing check
    v = recheck_witness(row)
    assert v["reward_reproduced"] != row["grade"]["reward"]
    assert v["witness"] == "DRIFT"  # fails closed: recorded reward no longer re-derives


def test_mapped_row_feeds_unchanged_flywheel():
    mapped = to_gradable_row(_row())
    # exactly the keys data_flywheel._spec_fields reads
    assert {"task_id", "prompt", "solution", "hidden_tests"} <= set(mapped)
    cc = data_flywheel.criterion_conservation([mapped])
    assert cc["schema"] == "data-flywheel.criterion-conservation/1"
    assert cc["tasks"] == 1
    assert cc["conservation_ratio"] > 1.0
    my = data_flywheel.manufactured_yield([mapped])
    assert my["gradable_triples"] == 1


def test_broken_seal_is_refused(tmp_path):
    row = _row()
    row["prompt"] = "a different prompt"   # mutate body but keep the old row_hash
    p = tmp_path / "data.jsonl"
    p.write_text(json.dumps(row, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="seal"):
        load_forum_jsonl(p)


def test_valid_row_loads_and_rechecks(tmp_path):
    # a genuinely sealed row (re-sealed after a legitimate change) loads and MATCHes
    row = _row()
    p = tmp_path / "data.jsonl"
    p.write_text(json.dumps(row, sort_keys=True) + "\n", encoding="utf-8")
    loaded = load_forum_jsonl(p)
    assert len(loaded) == 1
    assert recheck_witness(loaded[0])["witness"] == "MATCH"


def test_only_witnessed_rows_are_counted():
    # the honest yield: a batch of two rows, one tampered -> only the MATCH counts
    good = _row()
    bad = copy.deepcopy(good)
    bad["trajectory"]["entries"][1]["actor"] = "tampered"
    admitted = [r for r in (good, bad) if recheck_witness(r)["witness"] == "MATCH"]
    assert len(admitted) == 1
    my = data_flywheel.manufactured_yield([to_gradable_row(r) for r in admitted])
    assert my["gradable_triples"] == 1  # witnessed is COMPUTED, not asserted
