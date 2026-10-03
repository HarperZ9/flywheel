"""overrides_report.py -- per-rule override rates, reason codes and outcome checks.

Reads one record store and joins each hold to the owner's decision and to any
later outcome record. For every rule (or the judge) that raised a hold it
counts approvals, rejections, terminations and expiries, the override rate
(approvals over owner decisions), the reason codes owners gave, and how many
overrides a later check found right or wrong. Two alarms are raised: when more
than one owner decision in ten is coded "other" (the fixed list is missing a
reason) and when owner decisions carry no code at all.
"""
from __future__ import annotations

from collections import Counter, defaultdict

from .overrides import OUTCOME_SCHEMA
from .records import DECISION_SCHEMA, HOLD_SCHEMA, HoldStore

OWNER_DECISIONS = ("APPROVED_ONCE", "REJECTED", "TERMINATED")
OTHER_ALARM_SHARE = 0.10
DOES_NOT_PROVE = (
    "Counts what owners decided and what later checks recorded. An override rate "
    "does not show whether a rule is wrong; outcomes checked by the decider are "
    "self-checks and are counted apart.")


def _rule_keys(hold: dict) -> list:
    keys = list(hold.get("rule_hits", [])) + list(hold.get("trajectory_hits", []))
    if not keys and isinstance(hold.get("judge"), dict) and hold["judge"].get("state") != "off":
        keys = ["judge"]
    return keys or ["unattributed"]


def _empty() -> dict:
    return {"holds": 0, "decisions": Counter(), "reason_codes": Counter(),
            "outcomes": Counter(), "independent_outcomes": Counter()}


def _index(recs: list):
    holds = {r["seal"]["hex"]: r for r in recs if r.get("schema") == HOLD_SCHEMA and "seal" in r}
    decisions = [r for r in recs if r.get("schema") == DECISION_SCHEMA]
    outcomes = {r["decision_record_sha256"]: r for r in recs if r.get("schema") == OUTCOME_SCHEMA}
    return holds, decisions, outcomes


def _add(row: dict, dec: dict, outcome) -> None:
    row["decisions"][dec["decision"]] += 1
    if dec["decision"] in OWNER_DECISIONS:
        row["reason_codes"][dec.get("reason_code") or "uncoded"] += 1
    if outcome is not None:
        key = f"{dec['decision']}:{outcome['verdict_on_decision']}"
        row["outcomes"][key] += 1
        if not outcome.get("self_check"):
            row["independent_outcomes"][key] += 1


def _finish(row: dict) -> dict:
    d = row["decisions"]
    owner = sum(d[k] for k in OWNER_DECISIONS)
    return {"holds": row["holds"], "decisions": dict(d),
            "override_rate": round(d["APPROVED_ONCE"] / owner, 4) if owner else None,
            "reason_codes": dict(row["reason_codes"]), "outcomes": dict(row["outcomes"]),
            "independent_outcomes": dict(row["independent_outcomes"])}


def summarize(recs: list) -> dict:
    holds, decisions, outcomes = _index(recs)
    by_rule: dict = defaultdict(_empty)
    for hold in holds.values():
        for key in _rule_keys(hold):
            by_rule[key]["holds"] += 1
    codes: Counter = Counter()
    for dec in decisions:
        hold = holds.get(dec.get("hold_record_sha256", ""))
        if hold is None:
            continue
        outcome = outcomes.get(dec.get("seal", {}).get("hex", ""))
        for key in _rule_keys(hold):
            _add(by_rule[key], dec, outcome)
        if dec["decision"] in OWNER_DECISIONS:
            codes[dec.get("reason_code") or "uncoded"] += 1
    owner_total = sum(codes.values())
    other_share = round(codes["other"] / owner_total, 4) if owner_total else None
    return {"by_rule": {k: _finish(v) for k, v in sorted(by_rule.items())},
            "owner_decisions": owner_total, "reason_codes": dict(codes),
            "other_share": other_share,
            "other_alarm": bool(other_share is not None and other_share > OTHER_ALARM_SHARE),
            "uncoded_alarm": codes["uncoded"] > 0,
            "outcomes_recorded": len(outcomes),
            "does_not_prove": DOES_NOT_PROVE}


def report(home) -> dict:
    return summarize(HoldStore(home).read_all(tolerant=True))


def coder_agreement(codes_a: list, codes_b: list) -> dict:
    """Cohen's kappa between two owners who coded the same holds in the same order,
    plus each owner's share of "other". The P18 bar reads kappa >= 0.6 and an
    "other" share of at most 0.10 for both owners."""
    if len(codes_a) != len(codes_b) or not codes_a:
        raise ValueError("both owners must code the same, non-empty list of holds")
    n = len(codes_a)
    observed = sum(a == b for a, b in zip(codes_a, codes_b)) / n
    ca, cb = Counter(codes_a), Counter(codes_b)
    expected = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    kappa = 1.0 if expected == 1 else (observed - expected) / (1 - expected)
    return {"n": n, "observed": round(observed, 4), "kappa": round(kappa, 4),
            "other_share": [round(ca["other"] / n, 4), round(cb["other"] / n, 4)]}
