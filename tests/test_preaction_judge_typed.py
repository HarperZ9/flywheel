"""Layer 3 typed mode: four narrow questions, combined in code, ACT / ABSTAIN / ESCALATE.

Success criteria: a refusal-shaped answer set acts, an exfiltration-shaped set
escalates and a flat set abstains; the monitor holds on ABSTAIN (reason
judge_abstained) and on ESCALATE, and lets ACT through; an unavailable typed
judge holds as UNVERIFIABLE; the strictest of several judges wins; malformed
endpoint replies are unavailable; typed mode is the default only for a
SystemOne endpoint and cannot pair with a chat endpoint; configs written
before typed mode keep their digest; a typed hold re-derives without DRIFT.
"""
from __future__ import annotations

import json

import pytest

from harness.preaction import judge_typed as jt
from harness.preaction.contract import ALLOW, HOLD, UNVERIFIABLE
from harness.preaction.core import MonitorConfig
from harness.preaction.judge import JudgeConfig
from harness.preaction.verify import verify_store
from tests.preaction_fixtures import call, ctx, monitor

REFUSAL = {"effect": 0.03, "cautious": 0.9, "data": 0.03, "covered": 0.6}
EXFIL = {"effect": 0.85, "cautious": 0.05, "data": 0.8, "covered": 0.1}
FLAT = {"effect": 0.5, "cautious": 0.2, "data": 0.3, "covered": 0.3}


class FakeTyped:
    typed = True

    def __init__(self, answers=None, fail=False, name="t"):
        self.answers, self.fail, self.seen = answers, fail, []
        self.model_ref = f"fake-typed:{name}"

    def judge(self, payload):
        self.seen.append(payload)
        if self.fail:
            return {"state": "unavailable", "model_ref": self.model_ref, "detail": "timeout"}
        return jt.typed_result(self.model_ref, self.answers, input_sha256="0" * 64,
                               output_sha256="1" * 64)


def test_answer_shapes_map_to_the_three_outcomes():
    assert jt.decide(jt.p_hold(REFUSAL)) == "ACT"
    assert jt.decide(jt.p_hold(EXFIL)) == "ESCALATE"
    assert jt.decide(jt.p_hold(FLAT)) == "ABSTAIN"


@pytest.mark.parametrize("answers,verdict,reason", [
    (REFUSAL, ALLOW, None), (EXFIL, HOLD, "judge/typed_escalate"), (FLAT, HOLD, "judge_abstained")])
def test_monitor_holds_on_abstain_and_escalate(tmp_path, answers, verdict, reason):
    out = monitor(tmp_path, judges=[FakeTyped(answers)]).gate(call("read_file", path="a.py"), ctx())
    assert out.verdict == verdict
    ids = {r["id"] for r in out.assessment.reasons}
    assert (reason in ids) if reason else not ids


def test_act_cannot_release_a_rule_hit(tmp_path):
    judge = FakeTyped(REFUSAL)
    out = monitor(tmp_path, judges=[judge]).gate(call("run", cmd="git push --force origin main"), ctx())
    assert out.verdict == HOLD and judge.seen == []


def test_unavailable_typed_judge_holds_unverifiable(tmp_path):
    out = monitor(tmp_path, judges=[FakeTyped(fail=True)]).gate(call("read_file", path="a.py"), ctx())
    assert out.verdict == HOLD and out.assessment.coverage == UNVERIFIABLE


def test_strictest_outcome_wins_across_judges(tmp_path):
    judges = [FakeTyped(REFUSAL, name="a"), FakeTyped(EXFIL, name="b"), FakeTyped(FLAT, name="c")]
    out = monitor(tmp_path, judges=judges).gate(call("read_file", path="a.py"), ctx())
    assert out.assessment.judge["outcome"] == "ESCALATE"
    assert out.assessment.judge["model_ref"] == "fake-typed:b"


def test_receipt_block_carries_outcome_and_permille(tmp_path):
    out = monitor(tmp_path, judges=[FakeTyped(FLAT)]).gate(call("read_file", path="a.py"), ctx())
    block = out.assessment.preaction_block()["judge"]
    assert block["outcome"] == "ABSTAIN" and isinstance(block["p_hold_permille"], int)
    assert 450 <= block["p_hold_permille"] < 550


@pytest.mark.parametrize("body", [
    {"answers": {k: {"noul": 0.5} for k in ("effect", "cautious", "data")}},
    {"answers": {k: {"noul": 1.5} for k in jt.QUESTIONS}},
    {"answers": {k: {"noul": "0.5"} for k in jt.QUESTIONS}},
    {"answers": {k: {"noul": True} for k in jt.QUESTIONS}},
    {"answers": []}, []])
def test_malformed_replies_are_refused(body):
    assert jt.parse_answers(body) is None


def test_systemone_judge_posts_four_questions_and_parses(monkeypatch):
    j = jt.SystemOneJudge(JudgeConfig(endpoint="http://127.0.0.1:8000", model="clef-flash",
                                      protocol="systemone"))
    sent = {}

    def post(body):
        sent.update(json.loads(body))
        return json.dumps({"answers": {k: {"type": "noul", "noul": v} for k, v in EXFIL.items()}}).encode()
    monkeypatch.setattr(j, "_post", post)
    res = j.judge({"goal": "g", "call": {"tool": "run"}, "trajectory": {}})
    assert set(sent["questions"]) == set(jt.QUESTIONS) and isinstance(sent["state"], str)
    assert res["state"] == "typed" and res["outcome"] == "ESCALATE"
    assert j._url() == "http://127.0.0.1:8000/v1/systemone"


def test_unreachable_systemone_endpoint_is_unavailable():
    j = jt.SystemOneJudge(JudgeConfig(endpoint="http://127.0.0.1:9", model="m",
                                      protocol="systemone", timeout_s=0.5))
    assert j.judge({"goal": ""})["state"] == "unavailable"


def test_typed_is_default_for_systemone_and_refused_for_chat():
    cfg = MonitorConfig.from_dict({"judge": {"endpoint": "http://x", "model": "m", "protocol": "systemone"}})
    assert isinstance(cfg.build_judges()[0], jt.SystemOneJudge)
    with pytest.raises(ValueError):
        MonitorConfig.from_dict({"judge": {"endpoint": "http://x", "model": "m", "mode": "typed"}})
    with pytest.raises(ValueError):
        MonitorConfig.from_dict({"judge": {"endpoint": "http://x", "model": "m", "protocol": "grpc"}})


def test_old_configs_keep_their_digest():
    old = MonitorConfig.from_dict({"judge": {"endpoint": "http://x", "model": "m"}})
    body = old._digest_body()
    assert body["judge"] == {"endpoint": "http://x", "model": "m"}
    typed = MonitorConfig.from_dict({"judge": {"endpoint": "http://x", "model": "m", "protocol": "systemone"}})
    assert typed.digest() != old.digest()


def test_typed_hold_rederives_without_drift(tmp_path):
    mon = monitor(tmp_path, judges=[FakeTyped(EXFIL)])
    assert mon.gate(call("read_file", path="src/a.py"), ctx()).verdict == HOLD
    report = verify_store(tmp_path)
    assert report["verdict"] != "DRIFT" and report["judge_unverifiable"] == 1
