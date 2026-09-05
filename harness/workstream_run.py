"""workstream_run.py -- run the checks a workstream names, in dependency order.

The composition rule lives in workstream.py and decides nothing about when a
check runs. This module decides that, and the decision is worth stating: an
obligation whose dependency is refuted is never handed to a checker at all.

That is the whole economy of a large formalization. A stack of thirty thousand
lemmas where one near the bottom is withdrawn does not need thirty thousand
proof-assistant invocations to learn that the top is not established. It needs
one, and then a skip list. What comes back says which obligations were checked
and which were skipped for what reason, so a run that looks cheap can be told
apart from a run that was cheap because it gave up early.

Five checkers ship wired:

  lean         the Lean kernel, through harness.lean_oracle, which reports a
               missing toolchain as unverifiable rather than as a pass
  arithmetic   a quantity against a stated interval, with no expression
               evaluation anywhere in the path
  dimensional  a conversion inside one unit family, refusing across families
  readback     a recorded rendering of a formal statement, compared against its
               source by a person, in workstream_readback.py
  instrument   a device record against the reference file its driver ships, in
               workstream_instrument.py

The last two need something the workstream itself does not carry: the readings
recorded beside the declaration, and reference files the caller supplies. Both
settle unverifiable without them rather than passing, so wiring them is what
turns a carried claim into a checked one and never the reverse.

The other kinds in workstream.CHECKS take a caller-supplied checker. A kind with
nothing registered settles unverifiable and says so, which is the honest reading
of "this board has no way to decide that" and is never a pass.
"""
from __future__ import annotations

from harness.evidence_json import strict_load_json
from harness.workstream import CHECKS, Obligation, Workstream, WorkstreamError
from harness.workstream_instrument import instrument_checker
from harness.workstream_lean import _lean_environment, lean_checker
from harness.workstream_readback import readback_checker
from harness.workstream_receipt import workstream_receipt

# Re-exported so a caller wiring one checker does not have to know which module
# it moved to. The lean environment rule lives with the checker it belongs to.
__all__ = [
    "_lean_environment", "arithmetic_checker", "default_checkers",
    "dimensional_checker", "instrument_checker", "lean_checker",
    "load_workstream", "readback_checker", "run_workstream",
]

_TOLERANCE = 1e-9
_MAX_DOCUMENT = 32_000_000


def _pair(raw: object) -> tuple[str, str]:
    """Normalize what a checker returned into (verdict, detail)."""
    detail = ""
    value = raw
    if isinstance(raw, tuple):
        if len(raw) != 2:
            raise WorkstreamError("a checker returns a verdict or a (verdict, detail) pair")
        value, detail = raw
    value = getattr(value, "value", value)
    if not isinstance(value, str) or not isinstance(detail, str):
        raise WorkstreamError("a checker returns a verdict or a (verdict, detail) pair")
    return value, detail


def _payload(obligation: Obligation, fields: tuple[str, ...]) -> dict:
    """Parse a statement that is data rather than prose, and insist on its shape."""
    body = strict_load_json(obligation.statement, max_bytes=20_000)
    missing = [name for name in fields if name not in body]
    if missing:
        raise ValueError(f"the statement is missing {', '.join(missing)}")
    return body


def arithmetic_checker(obligation: Obligation) -> tuple[str, str]:
    """A quantity against a stated interval.

    No expression is evaluated here. A checker that ran arbitrary text from a
    statement would be an execution surface wearing the word arithmetic, and the
    interval is the part that carries the meaning anyway: a number with no
    interval is not a measurement.
    """
    try:
        body = _payload(obligation, ("value", "interval"))
        value = body["value"]
        interval = body["interval"]
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError("value must be a number")
        if (not isinstance(interval, list) or len(interval) != 2
                or any(not isinstance(bound, (int, float)) or isinstance(bound, bool)
                       for bound in interval)):
            raise ValueError("interval must be a pair of numbers")
    except (TypeError, ValueError) as exc:
        return "FAIL", f"the statement is not a readable interval claim: {exc}"
    low, high = sorted(interval)
    if low <= value <= high:
        return "PASS", f"{value} lies inside [{low}, {high}]"
    return "FAIL", f"{value} lies outside [{low}, {high}]"


def dimensional_checker(obligation: Obligation) -> tuple[str, str]:
    """A conversion inside one unit family, refusing across families.

    Crossing a family is a refusal rather than a guess. Litres do not become
    grams without a density, and a checker that bridged them quietly is how a
    dose error survives review.
    """
    from harness.domain_packs.units import convert

    try:
        body = _payload(obligation, ("value", "from", "to", "expected"))
        tolerance = body.get("tolerance", _TOLERANCE)
        if not isinstance(tolerance, (int, float)) or isinstance(tolerance, bool):
            raise ValueError("tolerance must be a number")
        got = convert(float(body["value"]), str(body["from"]), str(body["to"]))
        expected = float(body["expected"])
    except (LookupError, TypeError, ValueError) as exc:
        return "FAIL", f"the conversion does not hold: {exc}"
    if abs(got - expected) <= abs(tolerance):
        return "PASS", f"{body['value']} {body['from']} is {got} {body['to']}"
    return "FAIL", f"expected {expected} {body['to']}, the conversion gives {got}"


def default_checkers(readbacks: dict[str, dict] | None = None,
                     references: dict[str, dict] | None = None) -> dict:
    """The kinds this repository can decide on its own.

    Called bare, read-back and instrument obligations settle unverifiable and
    say what they were missing. That is the point of wiring them at all: the
    difference between a device claim nobody checked and one that was checked
    has to be visible in the receipt, not in whether the checker was present.
    """
    return {
        "lean": lean_checker,
        "arithmetic": arithmetic_checker,
        "dimensional": dimensional_checker,
        "readback": readback_checker(readbacks),
        "instrument": instrument_checker(references),
    }


def _decide(obligation: Obligation, checkers: dict) -> tuple[str, str]:
    """Run one obligation's checker and turn whatever happened into a verdict."""
    checker = checkers.get(obligation.check)
    if checker is None:
        return "UNVERIFIABLE", f"no checker is registered for the {obligation.check} kind"
    try:
        return _pair(checker(obligation))
    except WorkstreamError:
        raise
    except Exception as exc:  # noqa: BLE001 - recorded, not swallowed
        # A checker that crashed did not refute anything. Attributing its crash
        # to the statement would teach a reader that our environment's failure
        # was the candidate's error, so it lands as unverifiable with the text.
        return "UNVERIFIABLE", f"the checker raised {type(exc).__name__}: {exc}"


def run_workstream(workstream: Workstream, checkers: dict | None = None) -> dict:
    """Check what is worth checking, then settle the whole graph.

    Returns the workstream receipt with a `run` block beside it naming what was
    checked, what was skipped, and why. Nothing here decides a standing: the
    results go back to `settle`, which is the only place the composition rule
    lives.
    """
    registry = default_checkers() if checkers is None else dict(checkers)
    unknown = set(registry) - set(CHECKS)
    if unknown:
        raise WorkstreamError(f"unknown check kind {sorted(unknown)[0]}")
    results: dict[str, object] = {}
    details: dict[str, str] = {}
    satisfied: dict[str, bool] = {}
    ran: list[str] = []
    skipped: list[dict] = []
    for node_id in workstream.order:
        node = workstream.nodes[node_id]
        holes = [ref for ref in node.depends_on if not satisfied[ref]]
        if node.check == "assumed":
            # An assumption that names dependencies is conditional on them. If
            # what it rests on is broken it cannot satisfy its parent, or a
            # refuted sub-proof would launder itself through the assumption.
            satisfied[node_id] = not holes
            continue
        if holes:
            satisfied[node_id] = False
            skipped.append({"obligation_id": node_id, "unsatisfied_dependency": holes[0]})
            continue
        verdict, detail = _decide(node, registry)
        results[node_id] = verdict
        details[node_id] = detail
        satisfied[node_id] = verdict == "PASS"
        ran.append(node_id)
    receipt = workstream_receipt(workstream, results)
    for node_id, detail in details.items():
        receipt["obligations"][node_id]["detail"] = detail
    receipt["run"] = {
        "checked": len(ran),
        "skipped": len(skipped),
        "ran": ran,
        "skipped_for": skipped,
        "registered_kinds": sorted(registry),
    }
    return receipt


def load_workstream(document: str) -> tuple[Workstream, dict]:
    """Read a workstream declaration, and any results already recorded in it.

    The declaration is data a stranger can write, so every field is checked
    here rather than trusted. Results carried inside the document are for the
    settle path, where the checks ran somewhere else and this is the record
    being recomposed.
    """
    body = strict_load_json(document, max_bytes=_MAX_DOCUMENT)
    goal = body.get("goal")
    listed = body.get("obligations")
    if not isinstance(goal, str) or not isinstance(listed, list):
        raise WorkstreamError("a declaration carries a goal string and an obligations list")
    obligations: list[Obligation] = []
    results: dict[str, object] = {}
    for entry in listed:
        if not isinstance(entry, dict):
            raise WorkstreamError("every obligation is an object")
        depends_on = entry.get("depends_on", [])
        if not isinstance(depends_on, list):
            raise WorkstreamError("depends_on is a list of obligation ids")
        obligations.append(Obligation(
            obligation_id=entry.get("id", ""),
            statement=entry.get("statement", ""),
            check=entry.get("check", ""),
            environment=entry.get("environment", ""),
            depends_on=tuple(depends_on),
        ))
        if entry.get("result") is not None:
            results[obligations[-1].obligation_id] = entry["result"]
    return Workstream(obligations, goal=goal), results
