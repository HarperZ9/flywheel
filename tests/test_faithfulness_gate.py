"""Two judges, one witnessed disagreement. Judge choice moves published
faithfulness scores by 25+ points (lean-invention dossier), and the
field's habit is to average the judges into false confidence. This gate
records both verdicts per pair and reports agreement, disagreement, and
the rate: the disagreement IS the finding, never noise to smooth."""

from harness.faithfulness_gate import judge_pairs

PAIRS = [
    {"informal": "n plus zero equals n",
     "formal": "theorem a (n : Nat) : n + 0 = n := by omega"},
    {"informal": "addition commutes",
     "formal": "theorem b (n m : Nat) : n + m = m + n := by omega"},
    {"informal": "n plus one equals n",
     "formal": "theorem c (n : Nat) : n + 1 = n + 1 := rfl"},
]


def _judge_by_len(p):
    return len(p["informal"]) < 30


def _judge_yes(p):
    return True


def test_agreement_and_disagreement_are_both_witnessed():
    r = judge_pairs(PAIRS, judge_a=_judge_by_len, judge_b=_judge_yes,
                    names=("len-judge", "yes-judge"))
    assert r["schema"] == "flywheel.faithfulness-disagreement/v1"
    assert r["n_pairs"] == 3
    rows = r["rows"]
    assert all("judge_a" in x and "judge_b" in x for x in rows)
    agrees = sum(1 for x in rows if x["agree"])
    assert agrees + r["disagreements"] == 3
    assert r["disagreement_rate"] == round(r["disagreements"] / 3, 4)
    assert r["judges"] == ["len-judge", "yes-judge"]


def test_disagreements_name_their_pair():
    r = judge_pairs(PAIRS, judge_a=_judge_by_len, judge_b=_judge_yes,
                    names=("a", "b"))
    for x in r["rows"]:
        if not x["agree"]:
            assert x["informal"], "a disagreement must name its pair"


def test_a_crashing_judge_is_an_unverifiable_row_not_a_crash():
    def bad(p):
        raise RuntimeError("judge died")
    r = judge_pairs(PAIRS[:1], judge_a=bad, judge_b=_judge_yes,
                    names=("bad", "ok"))
    row = r["rows"][0]
    assert row["judge_a"] is None
    assert row["agree"] is False
    assert "RuntimeError" in row["note"]


def test_no_single_score_is_ever_synthesized():
    r = judge_pairs(PAIRS, judge_a=_judge_by_len, judge_b=_judge_yes,
                    names=("a", "b"))
    assert "score" not in r and "mean" not in r, \
        "averaging judges into one number is the failure this gate exists to refuse"
