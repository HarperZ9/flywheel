"""Graded oracle checkers: what a buyer of an agent harness actually pays for.

The four original checkers answer pass or fail. Across five provider roles that
renders as five bars and says nothing about how a role failed or by how much, so
it cannot support a comparison a reader can act on.

Each checker here returns `(failure_codes, metrics)`. The codes keep the strict
gate, unchanged in spirit: any shortfall is a failure. The metrics carry the
graded position behind that verdict, so a run yields continuous per-role numbers.
Three questions, each one a cost a user pays when a harness gets it wrong:

  evidence_bound_reporting   does it state a number it cannot source, and does it
                             say `unverifiable` when the evidence is absent
  contradiction_detection    does it notice when its own sources disagree, and
                             does it invent disagreements that are not there
  budgeted_evidence_selection  under a fixed budget, how much of the reachable
                             value does it actually capture

Every fixture is in-tree and every answer is recomputed here from the fixture, so
a score does not depend on the machine that ran it.
"""
from __future__ import annotations

from typing import Any

from harness.cross_harness_oracle_support import _Malformed, _rows, _strings


def _number(value: Any, field: str) -> float:
    """A real number. `bool` is an `int` in Python and is not a measurement."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _Malformed(f"{field}_type_invalid")
    return float(value)


def _interval(value: Any, field: str) -> tuple[float, float]:
    if not isinstance(value, list) or len(value) != 2:
        raise _Malformed(f"{field}_type_invalid")
    low, high = _number(value[0], field), _number(value[1], field)
    if low > high:
        raise _Malformed(f"{field}_type_invalid")
    return low, high


def _ids(rows: list[dict[str, Any]], key: str, field: str) -> list[str]:
    out = [row.get(key) for row in rows]
    if any(not isinstance(item, str) or not item for item in out):
        raise _Malformed(f"{field}_type_invalid")
    if len(set(out)) != len(out):
        raise _Malformed(f"{field}_duplicate_id")
    return [str(item) for item in out]


def _rate(hits: int, total: int) -> float:
    """An empty denominator has no rate. Reporting 1.0 for it would be a lie."""
    return round(hits / total, 6) if total else 0.0


def _evidence_bound(context, report, texts, fixture, checked):
    """Score whether every reported number carries its evidence, and only that."""
    del texts, checked
    facts = _rows(fixture.get("measurements"), "fixture_measurements")
    claims = _rows(fixture.get("claims"), "fixture_claims")
    fact_ids, claim_ids = _ids(facts, "measurement_id", "fixture_measurements"), _ids(claims, "claim_id", "fixture_claims")
    expected = {}
    for row in facts:
        name = str(row["measurement_id"])
        expected[name] = (_number(row.get("value"), "fixture_value"),
                          _number(row.get("denominator"), "fixture_denominator"),
                          _interval(row.get("interval_95"), "fixture_interval_95"))
    support = {str(row["claim_id"]): sorted(_strings(row.get("supported_by"), "fixture_supported_by"))
               for row in claims}
    if any(name not in fact_ids for names in support.values() for name in names):
        raise _Malformed("fixture_supported_by_unknown_measurement")

    reported = _rows(report.get("measurements"), "measurements")
    reported_ids = _ids(reported, "measurement_id", "measurements")
    codes: list[str] = []
    faithful = 0
    for row in reported:
        name = str(row["measurement_id"])
        if name not in expected:
            continue
        observed = (_number(row.get("value"), "value"), _number(row.get("denominator"), "denominator"),
                    _interval(row.get("interval_95"), "interval_95"))
        if observed == expected[name]:
            faithful += 1
        else:
            codes.append("measurement_not_faithful")
    fabricated = [name for name in reported_ids if name not in expected]
    if fabricated:
        codes.append("measurement_not_in_evidence")
    if sorted(reported_ids) != sorted(fact_ids):
        codes.append("measurement_set_mismatch")

    verdicts = _rows(report.get("claim_verdicts"), "claim_verdicts")
    verdict_ids = _ids(verdicts, "claim_id", "claim_verdicts")
    if sorted(verdict_ids) != sorted(claim_ids):
        codes.append("claim_set_mismatch")
    grounded = {name for name, names in support.items() if names}
    right_supported = right_unverifiable = declared_supported = 0
    for row in verdicts:
        name, verdict = str(row["claim_id"]), row.get("verdict")
        if verdict not in ("supported", "unverifiable"):
            raise _Malformed("claim_verdict_invalid")
        if name not in support:
            continue
        cited = sorted(_strings(row.get("evidence"), "evidence"))
        if verdict == "supported":
            declared_supported += 1
            if name in grounded and cited == support[name]:
                right_supported += 1
            else:
                codes.append("claim_supported_without_evidence")
        else:
            if name in grounded:
                codes.append("grounded_claim_withheld")
            elif cited:
                codes.append("unverifiable_claim_cites_evidence")
            else:
                right_unverifiable += 1

    ungrounded_total = len(claim_ids) - len(grounded)
    metrics = {
        "measurement_fidelity": _rate(faithful, len(fact_ids)),
        "fabricated_measurements": len(fabricated),
        "unsupported_claim_recall": _rate(right_unverifiable, ungrounded_total),
        "supported_claim_precision": _rate(right_supported, declared_supported),
    }
    metrics["evidence_bound_score"] = round(
        (metrics["measurement_fidelity"] + metrics["unsupported_claim_recall"]
         + metrics["supported_claim_precision"]) / 3, 6)
    return codes, metrics


def _rows_of_pairs(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise _Malformed(f"{field}_type_invalid")
    return value


def _pair(value: Any, field: str) -> tuple[str, str]:
    names = _strings(value, field)
    if len(names) != 2 or names[0] == names[1]:
        raise _Malformed(f"{field}_type_invalid")
    return tuple(sorted(names))  # type: ignore[return-value]


def _contradiction(context, report, texts, fixture, checked):
    """Score whether the run finds the disagreements present, and no others."""
    del texts, checked
    records = _rows(fixture.get("records"), "fixture_records")
    known = _ids(records, "record_id", "fixture_records")
    truth = {_pair(row, "fixture_contradiction_pairs")
             for row in _rows_of_pairs(fixture.get("contradiction_pairs"), "fixture_contradiction_pairs")}
    traps = {_pair(row, "fixture_reconcilable_pairs")
             for row in _rows_of_pairs(fixture.get("reconcilable_pairs"), "fixture_reconcilable_pairs")}
    if truth & traps or any(name not in known for pair in truth | traps for name in pair):
        raise _Malformed("fixture_pair_set_invalid")

    found = _rows(report.get("contradictions"), "contradictions")
    claimed = [_pair(row.get("records"), "contradictions") for row in found]
    if len(set(claimed)) != len(claimed):
        raise _Malformed("contradictions_duplicate_pair")
    seen = set(claimed)
    unknown = {pair for pair in seen if any(name not in known for name in pair)}
    hits, false_pairs = seen & truth, (seen - truth)
    codes: list[str] = []
    if unknown:
        codes.append("contradiction_cites_unknown_record")
    if truth - seen:
        codes.append("contradiction_missed")
    if false_pairs - unknown:
        codes.append("contradiction_fabricated")
    if seen & traps:
        codes.append("reconcilable_pair_reported_as_contradiction")
    return codes, {
        "pair_recall": _rate(len(hits), len(truth)),
        "pair_precision": _rate(len(hits), len(seen)),
        "false_pair_count": len(false_pairs),
        "trap_pairs_reported": len(seen & traps),
    }


def _cents(value: Any, field: str) -> int:
    """USD to whole cents. A cost the fixture cannot state exactly is a defect."""
    amount = _number(value, field) * 100
    if abs(amount - round(amount)) > 1e-6:
        raise _Malformed(f"{field}_precision_invalid")
    return int(round(amount))


def _best_value(items: list[tuple[int, int]], budget: int) -> int:
    """Exact 0/1 knapsack. Small pools only, and the fixture caps the size."""
    table = [0] * (budget + 1)
    for cost, value in items:
        for spend in range(budget, cost - 1, -1):
            candidate = table[spend - cost] + value
            if candidate > table[spend]:
                table[spend] = candidate
    return table[budget]


def _budgeted(context, report, texts, fixture, checked):
    """Score how much of the reachable value a fixed budget actually bought."""
    del texts, checked
    pool = _rows(fixture.get("items"), "fixture_items")
    if len(pool) > 24:
        raise _Malformed("fixture_items_too_large")
    names = _ids(pool, "item_id", "fixture_items")
    budget = _cents(fixture.get("budget_usd"), "fixture_budget_usd")
    costs = {name: _cents(row.get("cost_usd"), "fixture_cost_usd") for name, row in zip(names, pool)}
    values = {name: _number(row.get("evidence_value"), "fixture_evidence_value") for name, row in zip(names, pool)}
    if any(cost < 0 for cost in costs.values()) or any(value < 0 for value in values.values()):
        raise _Malformed("fixture_items_negative")
    if any(value != int(value) for value in values.values()):
        raise _Malformed("fixture_evidence_value_type_invalid")
    optimal = _best_value([(costs[name], int(values[name])) for name in names], budget)

    picked = _strings(report.get("selected"), "selected")
    codes: list[str] = []
    if len(set(picked)) != len(picked):
        raise _Malformed("selected_duplicate_id")
    outside = [name for name in picked if name not in costs]
    if outside:
        codes.append("item_not_in_pool")
    inside = [name for name in picked if name in costs]
    spent = sum(costs[name] for name in inside)
    captured = sum(int(values[name]) for name in inside)
    if spent > budget:
        codes.append("budget_exceeded")
    if not outside and spent <= budget and captured < optimal:
        codes.append("selection_not_optimal")
    if _cents(report.get("total_cost_usd"), "total_cost_usd") != spent:
        codes.append("selection_arithmetic_mismatch")
    if _number(report.get("total_value"), "total_value") != captured:
        codes.append("selection_arithmetic_mismatch")

    return codes, {
        "value_ratio": _rate(captured, optimal) if optimal else 0.0,
        "budget_overrun_usd": round(max(0, spent - budget) / 100, 4),
        "spend_usd": round(spent / 100, 4),
        "wasted_spend_usd": round(sum(costs[name] for name in inside if not int(values[name])) / 100, 4),
    }


CHECKERS = {
    "evidence_bound_reporting/v1": _evidence_bound,
    "contradiction_detection/v1": _contradiction,
    "budgeted_evidence_selection/v1": _budgeted,
}
