"""The backend registry, the read contract, the five controls, the lexical rule
and the scorer seam. Synthetic inputs only."""
import io
import re
import sys
from collections import Counter

import pytest

from harness import decision_backends as backends
from harness.classifier_workflows import score_workflow_batch
from harness.decision_backends.controls import CONTROL_ARMS, make_controls, uniform
from harness.decision_backends.lexical import FLOOR_P, MENTION_P, LexicalBackend, relevance
from tests.decision_bench_fixtures import PATH_ARM, make_items, question

ITEMS = make_items("calibration", 250)
NOUL = question("pkg/a.py", "note")


def _by_arm():
    return dict(make_controls(ITEMS, ["false"], seed=1709, coverage=.3))


def _picks(backend, items=ITEMS):
    rows, _ = backends.read_items(backend, items)
    return {r["item_id"]: max(r["raw"], key=r["raw"].get) for r in rows}


def test_resolve_names_every_builtin_arm_and_refuses_unknown_specs():
    assert [name for name, _ in backends.resolve("controls", items=ITEMS,
                                                 act_on=["false"])] == list(CONTROL_ARMS)
    assert [name for name, _ in backends.resolve("lexical")] == ["lexical"]
    for bad in ("", "lexicon", "module:os", "module:os:path:join", "module:../x:y", None):
        with pytest.raises(ValueError):
            backends.resolve(bad)


def test_a_module_arm_is_imported_only_when_resolved(tmp_path, monkeypatch):
    (tmp_path / "decide_lazy_arm.py").write_text(
        "from harness.decision_backends.lexical import LexicalBackend\n"
        "def make():\n    return LexicalBackend()\n"
        "def not_a_backend():\n    return object()\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.delitem(sys.modules, "decide_lazy_arm", raising=False)
    assert "decide_lazy_arm" not in sys.modules
    [(name, backend)] = backends.resolve("module:decide_lazy_arm:make")
    assert name == "module:decide_lazy_arm:make" and "decide_lazy_arm" in sys.modules
    assert isinstance(backend, backends.DecisionBackend)
    with pytest.raises(ValueError):
        backends.resolve("module:decide_lazy_arm:not_a_backend")
    [(_, fixture_arm)] = backends.resolve(PATH_ARM)
    assert fixture_arm.backend_id == "fixture:path-arm"


def _answer(raw, mass=1.0, agree=True):
    return {"answers": {"q": {"raw": raw, "label_mass": mass, "order_agreement": agree}}}


@pytest.mark.parametrize("result, code", [
    ({"answers": {}}, "answer_keys"),
    (_answer({"true": 0.5, "false": 0.4}), "raw_sum"),
    (_answer({"true": 0.5, "maybe": 0.5}), "raw_labels"),
    (_answer({"true": 1.5, "false": -0.5}), "raw_value"),
    (_answer({"true": 1.0}, mass=0.0), "label_mass"),
    (_answer({"true": 1.0}, agree=1), "order_agreement"),
    ({**_answer({"true": 1.0}), "gpu_seconds": -1}, "gpu_seconds"),
    ({**_answer({"true": 1.0}), "usage": {"input_tokens": -1, "output_tokens": 0}}, "usage"),
    ({**_answer({"true": 1.0}), "weights_sha256": 7}, "provenance"),
    ([], "result_shape"),
])
def test_check_read_refuses_malformed_results_with_fixed_codes(result, code):
    with pytest.raises(backends.BackendResultError) as refused:
        backends.check_read(result, {"q": NOUL})
    assert str(refused.value) == code


def test_check_read_fills_absent_labels_and_renormalizes():
    got = backends.check_read(_answer({"true": 0.6004, "none": 0.4}), {"q": NOUL})
    raw = got["answers"]["q"]["raw"]
    assert set(raw) == {"true", "false", "none"} and raw["false"] == 0.0
    assert sum(raw.values()) == pytest.approx(1.0, abs=1e-12)


class _Spy:
    backend_id = "spy"

    def __init__(self, fail_unit=None):
        self.calls, self.fail_unit = [], fail_unit

    def capabilities(self):
        return {"question_types": ["noul"]}

    def read(self, state, questions, *, deadline_ms):
        self.calls.append((state, questions, deadline_ms))
        if self.fail_unit and self.fail_unit in state:
            raise RuntimeError("synthetic failure")
        return {"answers": {q: {"raw": {"true": 1.0}, "label_mass": 1.0,
                                "order_agreement": True} for q in questions}}


def test_read_items_sends_no_label_and_one_call_per_unit():
    spy = _Spy()
    rows, units = backends.read_items(spy, ITEMS[:40], deadline_ms=1234)
    assert len(spy.calls) == 10 and len(units) == 10 and len(rows) == 40
    for state, questions, deadline in spy.calls:
        assert deadline == 1234
        text = repr(questions)
        assert all(key not in text for key in ("target", "certification_unit", "tokens"))
    assert all(r["raw"] == {"true": 1.0, "false": 0.0, "none": 0.0} for r in rows)


class _IdCheat:
    """Answers true for a question id that holds 'pos' or comes first in the
    call. It exploits labels a builder leaked into ids or order."""
    backend_id = "cheat"

    def __init__(self):
        self.keys = []

    def capabilities(self):
        return {"question_types": ["noul"]}

    def read(self, state, questions, *, deadline_ms):
        keys = list(questions)
        self.keys.append(keys)
        return {"answers": {q: {"raw": {"true": 1.0} if "pos" in q or q == keys[0]
                                else {"false": 1.0}, "label_mass": 1.0,
                                "order_agreement": True} for q in keys}}


def test_labels_planted_in_item_ids_and_order_never_reach_a_backend():
    leaky = [dict(i, item_id=i["unit_id"] + ("-pos" if i["target"] == "true"
                                            else f"-neg{n}"))
             for n, i in enumerate(ITEMS)]          # the positive also comes first
    cheat = _IdCheat()
    rows, _ = backends.read_items(cheat, leaky)
    seen = [k for call in cheat.keys for k in call]
    assert len(seen) == len(leaky) == len(set(seen))
    assert all(re.fullmatch(r"q[0-9a-f]{24}", k) for k in seen)
    assert all(call == sorted(call) for call in cheat.keys)
    hits = [r["raw"]["true"] == 1.0 for r in rows if r["target"] == "true"]
    # With ids or order leaking, the cheat finds every positive; opaque keys in
    # hash order leave it the 1-in-4 chance of the first slot.
    assert len(hits) == 250 and sum(hits) / len(hits) < 0.4


def test_the_label_reading_controls_still_find_their_items_under_opaque_keys():
    arms = dict(make_controls(ITEMS, ["false"]))
    rows, _ = backends.read_items(arms["control.oracle"], ITEMS)
    assert all(r["raw"][r["target"]] == 1.0 for r in rows)


def test_a_failing_unit_is_recorded_logged_and_abstains():
    log = io.StringIO()
    rows, units = backends.read_items(_Spy(fail_unit="cal0002w"), ITEMS[:16], log=log)
    failed = [r for r in rows if r["unit_id"] == "cal0002"]
    assert [r["error_type"] for r in failed] == ["RuntimeError"] * 4
    assert all(r["raw"] is None for r in failed)
    assert [u["error_type"] for u in units].count("RuntimeError") == 1
    assert "spy failed on unit cal0002: RuntimeError" in log.getvalue()
    assert "synthetic failure" not in log.getvalue()


def test_an_exception_name_built_from_data_never_reaches_rows_or_the_log():
    leaky = type("secret token value", (RuntimeError,), {})

    class _Leaky(_Spy):
        def read(self, state, questions, *, deadline_ms):
            raise leaky("synthetic failure")

    log = io.StringIO()
    rows, units = backends.read_items(_Leaky(), ITEMS[:4], log=log)
    assert [r["error_type"] for r in rows] == ["Exception"] * 4
    assert units[0]["error_type"] == "Exception"
    assert "secret" not in log.getvalue() and "secret" not in repr((rows, units))


def test_questions_outside_capabilities_are_marked_not_read():
    items = [dict(ITEMS[0], question={"type": "score", "instructions": "rate",
                                      "criteria": ["low", "high"]}, target="1")]
    spy = _Spy()
    rows, _ = backends.read_items(spy, items)
    assert spy.calls == [] and rows[0]["error_type"] == "backend_capability"


def test_include_all_never_acts_and_exclude_all_always_acts():
    arms = _by_arm()
    assert set(_picks(arms["control.include_all"]).values()) == {"true"}
    assert set(_picks(arms["control.exclude_all"]).values()) == {"false"}


def test_random_control_hits_its_coverage_and_ignores_order_and_labels():
    arms = _by_arm()
    picks = _picks(arms["control.random"])
    share = sum(p == "false" for p in picks.values()) / len(picks)
    assert 0.25 < share < 0.35
    assert picks == _picks(arms["control.random"], list(reversed(ITEMS)))
    flipped = [dict(i, target="true") for i in ITEMS]
    again = dict(make_controls(flipped, ["false"], coverage=.3))["control.random"]
    assert _picks(again) == picks
    assert uniform(1709, "x") == uniform(1709, "x") != uniform(1710, "x")


def test_label_shuffle_keeps_label_counts_but_not_labels():
    shuffled = _picks(_by_arm()["control.label_shuffle"])
    truth = {i["item_id"]: i["target"] for i in ITEMS}
    assert Counter(shuffled.values()) == Counter(truth.values())
    agree = sum(shuffled[k] == truth[k] for k in truth) / len(truth)
    assert agree < 0.8         # a faithful copy would agree on every item


def test_oracle_matches_truth_and_only_label_readers_say_so():
    arms = _by_arm()
    assert _picks(arms["control.oracle"]) == {i["item_id"]: i["target"] for i in ITEMS}
    sees = {name: b.capabilities()["sees_labels"] for name, b in arms.items()}
    assert sees == {"control.include_all": False, "control.exclude_all": False,
                    "control.random": False, "control.label_shuffle": True,
                    "control.oracle": True}


def test_lexical_reads_path_mentions_and_overlap():
    text = "Does the change described in the state require editing harness/io.py (reader helper)?"
    assert relevance("Fix harness/io.py so it reads", text) == MENTION_P
    assert relevance("io.py was wrong", text) == MENTION_P
    assert relevance("studio.py was wrong", text) == FLOOR_P
    assert relevance("unrelated words entirely", text) == FLOOR_P
    assert relevance("the reader helper needs care", text) == pytest.approx(FLOOR_P + 0.8 * 2 / 3)
    stem = "Does the change described in the state require editing pkg/workflows.py?"
    assert relevance("workflows now retry", stem) == MENTION_P


def test_lexical_answers_noul_and_choice_and_refuses_score():
    lex = LexicalBackend()
    choice = {"type": "choice", "instructions": "pick",
              "criteria": {"alpha": "first reader", "beta": "second writer"}}
    out = backends.check_read(lex.read("the reader broke", {"n": NOUL, "c": choice}),
                              {"n": NOUL, "c": choice})
    raw = out["answers"]["c"]["raw"]
    assert raw["alpha"] > raw["beta"] and raw["__none__"] == 0.0
    assert out["answers"]["n"]["raw"]["none"] == 0.0
    with pytest.raises(ValueError):
        lex.read("x", {"s": {"type": "score", "instructions": "r", "criteria": ["a", "b"]}})
    assert "score" not in lex.capabilities()["question_types"]


def _decision_request(eligible):
    return {"schema": "flywheel.decision-request/v1", "decision_ref": "pick_tool",
            "state": "the reader helper failed", "evidence_refs": [],
            "choices": [{"id": "reader", "description": "reader helper"},
                        {"id": "writer", "description": "writer"},
                        {"id": "shell", "description": "shell"}],
            "eligible_choice_ids": eligible}


def test_as_scorer_plugs_any_backend_into_the_workflow_seam():
    packets = [{"task_family": "tool_choice", "request": _decision_request(["reader", "writer"])}]
    [result] = score_workflow_batch(packets, backends.as_scorer(LexicalBackend()))
    assert result["status"] == "scored_shadow" and result["fallback_required"] is True
    rows = {r["choice_id"]: r for r in result["scores"]["scores"]}
    assert rows["shell"]["eligible"] is False and rows["shell"]["probability_like"] == 0
    assert rows["__abstain__"]["probability_like"] == 0.0     # lexical puts no mass on none
    assert rows["reader"]["probability_like"] > rows["writer"]["probability_like"]
    assert result["scores"]["model_ref"] == "lexical:path-overlap-v1"
