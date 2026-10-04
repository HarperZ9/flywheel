"""Exact Shapley over sources, and the placebo rate built on it."""
from __future__ import annotations

import json
from fractions import Fraction
from pathlib import Path

import pytest

from harness import attribution_far as af
from harness import shapley_far as sf

ITEMS = (Path(__file__).resolve().parents[1] / "project-docs" / "records"
         / "2026-10-04-shapley-placebo" / "items-v1.json")


def test_dictator_gets_all_credit_and_null_players_none():
    phi = sf.shapley_exact(4, lambda m: 1 if m & 1 else 0)
    assert phi == [1, 0, 0, 0]


def test_symmetric_players_split_credit_and_duplicates_halve():
    # v = 1 when player 0 or its duplicate 1 is present: the copies split the credit.
    phi = sf.shapley_exact(3, lambda m: 1 if m & 0b011 else 0)
    assert phi == [Fraction(1, 2), Fraction(1, 2), 0]


def test_glove_game_matches_the_textbook_values():
    # One left glove (0), two right gloves (1, 2): a pair is worth 1.
    phi = sf.shapley_exact(3, lambda m: 1 if (m & 1) and (m & 0b110) else 0)
    assert phi == [Fraction(2, 3), Fraction(1, 6), Fraction(1, 6)]


def test_n_is_bounded():
    with pytest.raises(sf.ShapleyError):
        sf.shapley_exact(sf.MAX_N + 1, lambda m: 0)


@pytest.mark.parametrize("output,accepted,expected", [
    ("Six feet.", ["6", "six"], 1), ("16 feet", ["6", "six"], 0), ("sixty", ["six"], 0),
    ("23,000 feet", ["23000"], 1), ("the man-carrying pig", ["man carrying pig"], 1),
    ("Captain Lloyd", ["lloyd"], 1), ("I do not know", ["1817"], 0)])
def test_answer_value_is_a_whole_word_match(output, accepted, expected):
    assert sf.answer_value(output, accepted) == expected


def test_prompt_keeps_source_letters_across_coalitions():
    srcs = [{"text": "alpha"}, {"text": ""}, {"text": "gamma"}]
    p = sf.prompt("Q?", srcs, 0b110)
    assert "[Source B]\n(empty)" in p and "[Source C]\ngamma" in p and "alpha" not in p
    assert "(no sources)" in sf.prompt("Q?", srcs, 0)


def _item(roles):
    return {"item_id": "x", "sources": [{"role": r, "kind": k} for r, k in roles]}


def test_trials_flag_a_control_that_takes_credit():
    item = _item([("gold", "gold"), ("control", "empty"), ("control", "shuffled")])
    # The answer appears only when the shuffled control is present: a false credit.
    values = [1 if m & 0b100 else 0 for m in range(8)]
    trials = sf.item_trials(item, values)
    assert [t["attributed"] for t in trials] == [False, False, True]
    assert trials[2]["is_control"] and trials[0]["answerable"]


def test_trials_refuse_a_short_table():
    with pytest.raises(sf.ShapleyError):
        sf.item_trials(_item([("gold", "gold"), ("control", "empty")]), [0, 1, 1])


def _manifest():
    return sf.manifest("test", [{"path": "items-v1.json", "sha256": "0" * 64}])


def test_analyze_reports_wilson_intervals_and_the_shared_verdict():
    item = _item([("gold", "gold")] + [("control", "empty")] * 5)
    values = [1 if m & 1 else 0 for m in range(64)]
    trials = sf.item_trials(item, values)
    out = sf.analyze(trials, _manifest())
    assert out["verdict"] == af.RELIABLE
    assert out["false_attribution"]["k"] == "0" and out["false_attribution"]["n"] == "5"
    assert out["false_attribution"]["method"] == "wilson-95"
    assert float(out["false_attribution"]["upper"]) > 0.4  # five trials say little
    assert out["gold_detection_on_answerable"]["k"] == "1"
    assert sf.SHAPLEY_DOES_NOT_PROVE in out["does_not_prove"]


def test_the_preregistered_item_set_is_well_formed():
    data = json.loads(ITEMS.read_text(encoding="utf-8"))
    assert len(data["items"]) == 16
    for it in data["items"]:
        kinds = sorted(s["kind"] for s in it["sources"])
        assert kinds == ["empty", "gold", "irrelevant", "irrelevant", "shuffled", "shuffled"]
        for s in it["sources"]:
            if s["role"] == "control":
                assert not any(sf.answer_value(s["text"], [a]) for a in it["accepted"])
        gold = next(s for s in it["sources"] if s["kind"] == "gold")
        assert any(sf.answer_value(gold["text"], [a]) for a in it["accepted"]), it["item_id"]
