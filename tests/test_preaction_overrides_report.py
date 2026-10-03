"""Per-rule override report and the override CLI commands.

Success criteria: override rate per rule is approvals over owner decisions and
ignores expiries; reason codes and outcomes are counted per rule, with
self-checked outcomes kept out of the independent count; the "other" alarm
fires above one in ten and not at or below it; the uncoded alarm fires on an
owner decision with no code; approve takes --reason-code; outcome needs a
terminal and the typed seal prefix.
"""
from __future__ import annotations

import io
import json

from harness.preaction import cli, records
from harness.preaction.overrides import record_outcome
from harness.preaction.overrides_report import report
from tests.preaction_fixtures import Clock, call, ctx, monitor


def _hold_and_decide(mon, decision, code, n):
    held = mon.gate(call("run", cmd=f"git push --force origin b{n}"), ctx())
    mon.escalator.decide(held.hold_id, decision, decider="owner", reason_code=code)
    return records.HoldStore(mon.home).read_all()[-1]


def _store(tmp_path, plan):
    mon = monitor(tmp_path)
    return [_hold_and_decide(mon, d, c, n) for n, (d, c) in enumerate(plan)]


def test_override_rate_per_rule_ignores_expiry(tmp_path):
    clock = Clock()
    mon = monitor(tmp_path, clock=clock)
    for n, d in enumerate(["APPROVED_ONCE", "REJECTED", "REJECTED", "APPROVED_ONCE"]):
        _hold_and_decide(mon, d, "rule_false_positive", n)
    mon.gate(call("run", cmd="git push --force origin late"), ctx())
    clock.advance(31 * 60)
    mon.escalator.expire_due()
    rows = report(tmp_path)["by_rule"]
    row = next(v for v in rows.values() if v["holds"] == 5)
    assert row["override_rate"] == 0.5 and row["decisions"]["EXPIRED"] == 1


def test_outcomes_split_self_checks_from_independent(tmp_path):
    a, b = _store(tmp_path, [("APPROVED_ONCE", "wrong_target"), ("APPROVED_ONCE", "wrong_target")])
    record_outcome(tmp_path, Clock(), a["seal"]["hex"], "harm_observed", checked_by="owner")
    record_outcome(tmp_path, Clock(), b["seal"]["hex"], "no_harm_observed", checked_by="reviewer")
    row = next(iter(report(tmp_path)["by_rule"].values()))
    assert row["outcomes"] == {"APPROVED_ONCE:WRONG": 1, "APPROVED_ONCE:RIGHT": 1}
    assert row["independent_outcomes"] == {"APPROVED_ONCE:RIGHT": 1}


def test_other_alarm_threshold(tmp_path):
    plan = [("REJECTED", "scope_exceeded")] * 9 + [("REJECTED", "other")]
    _store(tmp_path, plan)
    rep = report(tmp_path)
    assert rep["other_share"] == 0.1 and rep["other_alarm"] is False


def test_other_alarm_fires_above_one_in_ten(tmp_path):
    _store(tmp_path, [("REJECTED", "scope_exceeded")] * 8 + [("REJECTED", "other")] * 2)
    assert report(tmp_path)["other_alarm"] is True


def test_uncoded_alarm(tmp_path):
    _store(tmp_path, [("REJECTED", "scope_exceeded"), ("APPROVED_ONCE", "")])
    rep = report(tmp_path)
    assert rep["uncoded_alarm"] is True and rep["reason_codes"]["uncoded"] == 1


def _cli(*argv, stdin="", isatty=False):
    out, err = io.StringIO(), io.StringIO()
    code = cli.main(list(argv), stdout=out, stderr=err, stdin=io.StringIO(stdin),
                    isatty=lambda: isatty)
    return code, out.getvalue(), err.getvalue()


def test_cli_approve_records_reason_code(tmp_path):
    mon = monitor(tmp_path, clock=cli._clock)
    held = mon.gate(call("run", cmd="git push --force"), ctx())
    code_ = mon.escalator.read_pending(held.hold_id)["confirm_code"]
    rc, _, _ = _cli("approve", held.hold_id, "--home", str(tmp_path), "--reason-code",
                    "rule_false_positive", stdin=code_ + "\n", isatty=True)
    assert rc == 0 and records.HoldStore(tmp_path).read_all()[-1]["reason_code"] == "rule_false_positive"


def test_cli_outcome_needs_terminal_and_seal_prefix(tmp_path):
    dec = _store(tmp_path, [("REJECTED", "wrong_target")])[0]
    seal = dec["seal"]["hex"]
    base = ("outcome", seal, "--home", str(tmp_path), "--evidence", "call_not_needed")
    assert _cli(*base)[0] == 2
    assert _cli(*base, stdin="zzzzzz\n", isatty=True)[0] == 1
    rc, out, _ = _cli(*base, stdin=seal[:6] + "\n", isatty=True)
    assert rc == 0 and json.loads(out.splitlines()[-1])["verdict_on_decision"] == "RIGHT"
    rc, out, _ = _cli("overrides", "--home", str(tmp_path), "--json")
    assert rc == 0 and json.loads(out)["outcomes_recorded"] == 1


def test_coder_agreement_kappa_matches_a_worked_example():
    from harness.preaction.overrides_report import coder_agreement
    a = ["wrong_target"] * 20 + ["scope_exceeded"] * 5 + ["wrong_target"] * 10 + ["scope_exceeded"] * 15
    b = ["wrong_target"] * 20 + ["wrong_target"] * 5 + ["scope_exceeded"] * 10 + ["scope_exceeded"] * 15
    out = coder_agreement(a, b)
    # 2x2 table 20/5/10/15 of 50: po = 0.7, pe = 0.5, kappa = 0.4
    assert out["observed"] == 0.7 and out["kappa"] == 0.4 and out["other_share"] == [0.0, 0.0]
