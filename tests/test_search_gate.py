"""Adaptive-effort gate in front of search.

Success criteria:
- the gate is off by default and best_of_n then draws all K candidates;
- first-pass stops after one draw when the temperature-0 candidate passes the
  visible suite, and draws all K when it fails;
- sequential stops at the first visible pass in proposal order;
- property: over every visible-verdict vector of length 4, each gate selects the
  same candidate as full search (the gate never changes the pick);
- paired mutation: a gate that stops after the first draw whatever its verdict
  breaks that property, so the property test has teeth;
- the decider still runs once on the pick and can reject it;
- the search stage payload records planned, drawn and skipped samples;
- records replay counts a row whose first sample disagrees with search as
  inconsistent, and refuses to replay the sequential gate from G4 records.
"""
from __future__ import annotations

import itertools

import pytest

from harness import search_gate
from harness.eval import VERIFIED_INFERENCE
from harness.oracle import OracleResult
from harness.proposer import ProposerOutput, prompt_hash
from harness.search import best_of_n
from harness.search_gate import (GATES, gated_draws, gated_pick, replay_logged,
                                 replay_record)
from harness.task import Task

RIGHT, WRONG = "right", "wrong"
TASK = Task(task_id="t", prompt="p", oracle="fn", oracle_cmd="fn", workdir=".",
            candidate_path="solution.py")


class Seq:
    model_ref = "seq"

    def __init__(self, texts):
        self.texts, self.calls = list(texts), 0

    def generate(self, prompt, *, seed, temperature, max_new_tokens, system=""):
        self.calls += 1
        return ProposerOutput(text=self.texts.pop(0), model_ref="seq", seed=seed,
                              prompt_hash=prompt_hash(prompt), cache="stub")


class Accepts:
    oracle_type = "fn"

    def __init__(self, good):
        self.good, self.calls = good, 0

    def verify(self, candidate, task):
        self.calls += 1
        ok = candidate in self.good
        return OracleResult(passed=ok, cmd="fn", output_hash="h", stdout_excerpt="",
                            rc=0 if ok else 1)


def _run(texts, gate, decide=None):
    prop = Seq(texts)
    res = best_of_n(TASK, prop, Accepts({RIGHT}), effort_gate=gate, decide=decide)
    return res, prop.calls


def test_gate_off_by_default_draws_all():
    assert VERIFIED_INFERENCE.effort_gate == "off"
    res, calls = _run([RIGHT, WRONG, WRONG, WRONG], "off")
    assert calls == 4 and len(res.candidates) == 4 and res.verdict == "PASS"


def test_first_pass_stops_after_one_when_first_passes():
    res, calls = _run([RIGHT, WRONG, WRONG, WRONG], "first-pass")
    assert calls == 1 and res.planned == 4 and res.accepted.text == RIGHT


def test_first_pass_draws_all_when_first_fails():
    res, calls = _run([WRONG, RIGHT, WRONG, WRONG], "first-pass")
    assert calls == 4 and res.accepted.text == RIGHT


def test_sequential_stops_at_first_pass():
    res, calls = _run([WRONG, RIGHT, WRONG, WRONG], "sequential")
    assert calls == 2 and res.accepted.temperature == 0.4


def test_no_pass_draws_all_and_keeps_honest_fail():
    res, calls = _run([WRONG, "w2 x", "w3 y z", "w4"], "sequential")
    assert calls == 4 and res.verdict in ("FAIL", "UNVERIFIABLE")


def _pick_is_unchanged():
    for bits in itertools.product([False, True], repeat=4):
        full = gated_pick("off", bits)
        for gate in GATES:
            if gated_pick(gate, bits) != full:
                return False
    return True


def test_property_gate_never_changes_the_pick():
    assert _pick_is_unchanged()


def test_paired_mutation_stop_regardless_of_verdict_is_caught(monkeypatch):
    monkeypatch.setattr(search_gate, "should_stop", lambda gate, i, ok: gate != "off")
    assert not _pick_is_unchanged()


def test_draw_counts():
    assert gated_draws("first-pass", [True, True, False, False]) == 1
    assert gated_draws("first-pass", [False, True, False, False]) == 4
    assert gated_draws("sequential", [False, False, True, False]) == 3
    assert gated_draws("off", [True, True, True, True]) == 4


def test_decider_still_runs_once_and_can_reject():
    decide = Accepts(set())
    res, calls = _run([RIGHT, WRONG, WRONG, WRONG], "first-pass", decide=decide)
    assert calls == 1 and decide.calls == 1 and res.verdict == "FAIL"


def test_unknown_gate_is_rejected():
    with pytest.raises(ValueError):
        _run([RIGHT], "eager")


def test_replay_logged_matches_truncation():
    out = replay_logged("sequential", [False, True, True, False], [False, False, True, True])
    assert out == {"draws": 2, "pick": 1, "held": False}


def test_replay_record_flags_inconsistent_first_sample():
    row = {"single_visible": True, "single_held": True, "search_held": False,
           "self_scored_accept": False}
    assert replay_record("first-pass", row) == {"draws": 1, "held": True,
                                                "consistent": False}
    with pytest.raises(ValueError):
        replay_record("sequential", row)


def test_search_stage_payload_records_skipped(tmp_path):
    from harness.chain import chain_to_dicts
    from harness.search_stage import run_search_stage
    chain = []
    cfg = VERIFIED_INFERENCE.__class__(name="v", n_candidates=4, effort_gate="first-pass")
    run_search_stage(TASK, "p", Seq([RIGHT, WRONG, WRONG, WRONG]), Accepts({RIGHT}),
                     cfg, chain)
    payload = next(s for s in chain_to_dicts(chain) if s["stage"] == "search")["payload"]
    assert payload["effort_gate"] == {"gate": "first-pass", "planned": 4, "drawn": 1,
                                      "skipped": 3}
