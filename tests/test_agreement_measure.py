"""Falsifiers for the majority-agreement measurement (x-likes item 7), scripted voters only."""
import importlib.util
import json
from pathlib import Path

import pytest

from harness import agreement_vote as av
from harness.checks import FAIL, run
from harness.checks.agreement import attach, signal

ROOT = Path(__file__).resolve().parent.parent
CORPUS = json.loads((ROOT / "tests/fixtures/checks/false_accepts_v1.json").read_text("utf-8"))


def _script():
    spec = importlib.util.spec_from_file_location("run_agreement_panel",
                                                  ROOT / "scripts" / "run_agreement_panel.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("text,vote", [
    ("CORRECT", av.CORRECT), ("wrong.", av.WRONG), ("The answer is: Correct", av.CORRECT),
    ("<think>maybe WRONG</think>CORRECT", av.CORRECT), ("CORRECT or WRONG", av.ABSTAIN),
    ("I cannot tell", av.ABSTAIN), ("", av.ABSTAIN), ("INCORRECT", av.ABSTAIN),
])
def test_parse_rule(text, vote):
    assert av.parse_vote(text) == vote


def test_strict_majority_and_abstains_count_against():
    assert av.accepts(["CORRECT", "CORRECT", "WRONG"])
    assert not av.accepts(["CORRECT", "ABSTAIN", "WRONG"])
    assert not av.accepts(["CORRECT", "CORRECT", "ABSTAIN", "WRONG"])
    assert av.accepts(["CORRECT"] * 3 + ["WRONG"] * 2)


def test_interval_and_mcnemar_known_values():
    assert av.clopper_pearson(0, 40) == (0.0, 0.0881)
    assert av.clopper_pearson(2, 40) == (0.0061, 0.1692)
    assert av.clopper_pearson(40, 40)[0] == 0.9119
    assert av.exact_mcnemar(0, 0) == 1.0
    assert round(av.exact_mcnemar(0, 10), 5) == 0.00195


def test_the_prompt_is_fixed_and_shows_the_case():
    it = CORPUS["items"][0]
    p = av.render_prompt(it["kind"], it["subject"], it["spec"])
    assert "CORRECT or WRONG" in p and json.dumps(it["subject"]) in p
    assert len(av.TEMPLATE_SHA256) == 64 and set(av.KIND_TEXT) == {i["kind"] for i in CORPUS["items"]}


class Counting:
    def __init__(self, answer):
        self.answer, self.calls = answer, 0

    def __call__(self, prompt):
        self.calls += 1
        return self.answer(prompt) if callable(self.answer) else self.answer


def test_votes_resume_without_calling_again(tmp_path):
    rows = tmp_path / "rows.jsonl"
    v = Counting("CORRECT")
    av.run_votes(CORPUS, {"a": v}, rows)
    assert v.calls == 80
    again = Counting("WRONG")
    out = av.run_votes(CORPUS, {"a": again}, rows)
    assert again.calls == 0 and len(out) == 80 and all(r["vote"] == av.CORRECT for r in out)


def test_a_failing_voter_is_an_abstain_with_its_reason(tmp_path):
    def broken(prompt):
        raise TimeoutError("no answer")
    out = av.run_votes(CORPUS, {"b": broken}, tmp_path / "rows.jsonl")
    assert all(r["vote"] == av.ABSTAIN and "TimeoutError" in r["error"] for r in out)


def _truth_voter():
    wrong = {av.render_prompt(i["kind"], i["subject"], i["spec"]) for i in CORPUS["items"]}
    return lambda prompt: "WRONG" if prompt in wrong else "CORRECT"


def test_summary_counts_against_scripted_panels(tmp_path):
    det = _script().deterministic(CORPUS)
    assert sum(det.values()) == 38
    voters = {"yes1": lambda p: "CORRECT", "yes2": lambda p: "CORRECT", "truth": _truth_voter()}
    rows = av.run_votes(CORPUS, voters, tmp_path / "rows.jsonl")
    yes = av.summarize(CORPUS, rows, ["yes1", "yes2", "truth"], det)
    assert yes["false_accepts"] == 40 and yes["false_rejects_on_fixed"] == 0
    assert yes["caught_by_checks_not_panel"] == 38 and yes["mcnemar_p"] < 0.001
    oracle = av.summarize(CORPUS, rows, ["truth"], det)
    assert oracle["false_accepts"] == 0 and oracle["caught_by_panel_not_checks"] == 2


def test_the_script_dry_run_calls_nothing(tmp_path, capsys):
    assert _script().main(["--out", str(tmp_path / "o")]) == 0
    assert "dry run" in capsys.readouterr().out and not (tmp_path / "o").exists()


def test_measure_writes_hashes_for_both_panels(tmp_path):
    s = _script()
    voters = {m: (lambda p: "WRONG") for m in "abcde"}
    result = s.measure(CORPUS, voters, tmp_path, [list("abc"), list("abcde")])
    assert len(result["corpus_sha256"]) == 64 and len(result["rows_sha256"]) == 64
    assert [p["false_accepts"] for p in result["panels"]] == [0, 0]
    assert [p["false_rejects_on_fixed"] for p in result["panels"]] == [40, 40]


def test_agreement_never_changes_a_verdict():
    it = CORPUS["items"][0]
    receipt = run(it["kind"], it["subject"], it["spec"])
    assert receipt.verdict == FAIL
    sig = signal(["a", "b", "c"], ["CORRECT"] * 3, av.TEMPLATE_SHA256)
    out = attach(receipt, sig)
    assert out["verdict"] == FAIL and out["signals"]["agreement"]["accepts"] is False
    assert sig.majority_says == "CORRECT"
    assert signal(["a", "b"], ["CORRECT", "WRONG"], "x").majority_says == "SPLIT"


def test_the_ollama_voter_talks_only_to_loopback():
    with pytest.raises(ValueError):
        av.ollama_voter("m", "http://10.0.0.5:11434")
