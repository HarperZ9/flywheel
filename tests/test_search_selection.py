"""Checker selection: the visible checker selects, the held-out checker decides.

Success criteria:
- with a decider, a candidate the visible check passes and the held-out check
  rejects ends FAIL, and the decider runs exactly once, on the pick only;
- false-success control: the same fixture through the self-scored path (the
  visible oracle selects and decides) ends PASS, so the fixture can tell the two
  paths apart;
- the pick is the first visible pass in proposal order (temperature 0.0 first);
- run_loop on a task with a held-out command records
  `selection: visible-selects-held-out-decides` and the decider's verdict, and
  refuses the visible-only cheat; a task without one records `self-scored`;
- pool arms: best_of_k strictly beats placebo_of_k when the visible check
  carries signal and ties it when the visible check is a coin; a self-scored
  best_of_k must be asked for by name.
"""
from __future__ import annotations

import hashlib
import json

import pytest

from harness.eval import VERIFIED_INFERENCE
from harness.loop import run_loop
from harness.oracle import OracleResult, PytestOracle
from harness.pool_arms import best_of_k, placebo_of_k
from harness.proposer import ProposerOutput, prompt_hash
from harness.search import HELD_OUT_DECIDES, SELF_SCORED, best_of_n
from harness.task import Task, load_task

CORRECT = "def add(a, b):\n    return a + b\n"
CHEAT = "def add(a, b):\n    return 4\n"          # passes add(2, 2) == 4 only


class FnOracle:
    oracle_type = "fn"

    def __init__(self, fn):
        self.fn, self.calls = fn, []

    def verify(self, candidate, task):
        self.calls.append(candidate)
        ok = bool(self.fn(candidate))
        digest = hashlib.sha256(f"{ok}{candidate}".encode()).hexdigest()[:16]
        return OracleResult(passed=ok, cmd="fn", output_hash=digest,
                            stdout_excerpt="", rc=0 if ok else 1)


class MapProposer:
    model_ref = "map"

    def __init__(self, by_temp):
        self.by_temp = by_temp

    def generate(self, prompt, *, seed, temperature, max_new_tokens, system=""):
        text = self.by_temp[round(temperature, 2)]
        return ProposerOutput(text=text, model_ref=self.model_ref, seed=seed,
                              prompt_hash=prompt_hash(prompt), cache="stub")


VISIBLE = FnOracle(lambda c: c in (CORRECT, CHEAT))
HELD = (lambda c: c == CORRECT)
TASK = Task(task_id="t", prompt="p", oracle="fn", oracle_cmd="fn", workdir=".",
            candidate_path="solution.py")


def test_decider_rejects_the_visible_only_pick_and_runs_once():
    decide = FnOracle(HELD)
    sr = best_of_n(TASK, MapProposer({0.0: CHEAT, 0.4: CORRECT, 0.8: CORRECT, 1.1: CHEAT}),
                   FnOracle(VISIBLE.fn), decide=decide)
    assert sr.selected.text == CHEAT and sr.selected.temperature == 0.0
    assert decide.calls == [CHEAT]
    assert sr.verdict == "FAIL" and sr.accepted is None
    assert sr.selection == HELD_OUT_DECIDES


def test_control_self_scored_path_accepts_the_same_cheat():
    sr = best_of_n(TASK, MapProposer({0.0: CHEAT, 0.4: CORRECT, 0.8: CORRECT, 1.1: CHEAT}),
                   FnOracle(VISIBLE.fn))
    assert sr.verdict == "PASS" and sr.accepted.text == CHEAT
    assert sr.selection == SELF_SCORED


def test_decider_accepts_a_correct_pick():
    sr = best_of_n(TASK, MapProposer({0.0: CORRECT, 0.4: CHEAT, 0.8: CHEAT, 1.1: CHEAT}),
                   FnOracle(VISIBLE.fn), decide=FnOracle(HELD))
    assert sr.verdict == "PASS" and sr.accepted.text == CORRECT


def test_no_visible_pass_never_calls_the_decider():
    decide = FnOracle(HELD)
    wrong = {t: f"def add(a, b):\n    return {t}\n" for t in (0.0, 0.4, 0.8, 1.1)}
    sr = best_of_n(TASK, MapProposer(wrong), FnOracle(VISIBLE.fn), decide=decide)
    assert decide.calls == [] and sr.verdict in ("FAIL", "UNVERIFIABLE")


def _task_dir(root, held_out: bool):
    skel = root / "skeleton"
    (skel / "tests").mkdir(parents=True)
    (skel / "heldout").mkdir()
    (skel / "solution.py").write_text("")
    (skel / "tests" / "test_visible.py").write_text(
        "from solution import add\n\ndef test_v():\n    assert add(2, 2) == 4\n")
    (skel / "heldout" / "test_held.py").write_text(
        "from solution import add\n\ndef test_h():\n    assert add(2, 3) == 5\n")
    meta = {"task_id": "sel", "prompt": "add", "oracle": "pytest",
            "oracle_cmd": "python -m pytest tests/ -q -p no:cacheprovider",
            "candidate_path": "solution.py", "seed": 0}
    if held_out:
        meta["held_out_cmd"] = "python -m pytest heldout/ -q -p no:cacheprovider"
    (root / "task.json").write_text(json.dumps(meta))
    return root


def _search_payload(result):
    return next(s for s in result.envelope.chain if s["stage"] == "search")["payload"]


@pytest.mark.parametrize("held_out", [True, False])
def test_run_loop_records_who_selected_and_who_decided(tmp_path, held_out):
    task = load_task(_task_dir(tmp_path / "task", held_out), workdir=tmp_path / "w")
    proposer = MapProposer({0.0: CHEAT, 0.4: CORRECT, 0.8: CORRECT, 1.1: CORRECT})
    r = run_loop(task, proposer, PytestOracle(), envelopes_dir=tmp_path / "env",
                 search=VERIFIED_INFERENCE)
    payload = _search_payload(r)
    if held_out:
        assert payload["selection"] == HELD_OUT_DECIDES
        assert payload["decision"]["verdict"] == "FAIL"
        assert not r.accepted
    else:
        assert payload["selection"] == SELF_SCORED
        assert "decision" not in payload
        assert r.accepted and r.envelope.candidate == CHEAT


class _Pool:
    def __init__(self, cands):
        self.cands = cands

    def task_ids(self):
        return sorted(self.cands)

    def candidates(self, t):
        return list(enumerate(self.cands[t]))


def _pool(n=40):
    # Slot 0 is wrong, slot 1 is right, in every task.
    return _Pool({f"t{i}": ["wrong", "right"] for i in range(n)})


def _right(text, _task):
    return text == "right"


def test_best_of_k_beats_placebo_when_the_visible_check_carries_signal():
    pool = _pool()
    bok = best_of_k(pool, _right, score=_right)
    plc = placebo_of_k(pool, _right, seed=7, accept_rate=0.5)
    assert bok["passes"] > plc["passes"]


def test_best_of_k_ties_placebo_when_the_visible_check_is_a_coin():
    pool = _pool()
    coin = (lambda _text, _task: True)          # accepts slot 0 every time
    bok = best_of_k(pool, coin, score=_right)
    plc = placebo_of_k(pool, _right, seed=7, accept_rate=1.0)   # also takes slot 0
    assert bok["passes"] == plc["passes"] == 0


def test_self_scored_best_of_k_must_be_asked_for():
    with pytest.raises(ValueError):
        best_of_k(_pool(), _right)
    assert best_of_k(_pool(), _right, self_scored=True)["scored_by"] == "selector"
