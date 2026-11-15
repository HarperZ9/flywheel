"""Per-family scoring runners: one child execution + parent-side comparison.

Each runner takes the agent's module source and the family's frozen entry,
executes the module through the family's child driver, and returns
``(outcome, score)`` where ``outcome`` feeds the environment's zero-weight
diagnostic metrics. Every comparison happens here in the parent; the child
only ever sees inputs.
"""

from __future__ import annotations

from .harness import runner


async def run_parser_family(module_source: str, entry: dict) -> tuple[dict, float]:
    result = await runner.run_child(
        "child_driver_parser.py",
        module_source,
        [p["recipe"] for p in entry["probes"]],
        wall_clock=60.0,
    )
    if not result.ok or result.payload is None:
        return {"skipped": result.failure or "child-failure"}, 0.0
    score = runner.match_fraction(
        result.payload["results"],
        [p["expect"] for p in entry["probes"]],
        [p["weight"] for p in entry["probes"]],
    )
    return {"results": result.payload["results"]}, score


async def run_rubric_family(module_source: str, entry: dict) -> tuple[dict, float]:
    """Serves rubric-contract (uniform fixtures) and rubric-repair (frozen
    kill-set/regression weights)."""
    contract = entry["contract"]
    result = await runner.run_child(
        "child_driver_rubric.py",
        module_source,
        {
            "contract": {
                "names": contract["names"],
                "weights": contract["weights"],
            },
            "fixtures": [p["fixture"] for p in entry["fixtures"]],
        },
        wall_clock=90.0,
    )
    if not result.ok or result.payload is None:
        return {"skipped": result.failure or "child-failure"}, 0.0
    gate = result.payload["gate"]
    outcome = {"results": result.payload["results"], "gate": gate}
    if not all(gate.values()):
        return outcome, 0.0
    score = runner.match_fraction(
        result.payload["results"],
        [p["expect"] for p in entry["fixtures"]],
        [p.get("weight", 1.0) for p in entry["fixtures"]],
    )
    return outcome, score


def _script_credit(got: object, want: dict) -> float:
    """Full credit for a fully matching script; 0.5 for a matching transcript
    with wrong reward/metrics/stop_reason; else zero."""
    if not isinstance(got, dict) or "error" in got:
        return 0.0

    def matches(key: str) -> bool:
        return runner.match_fraction([got.get(key)], [want[key]]) == 1.0

    if not matches("transcript"):
        return 0.0
    if matches("reward") and matches("metrics") and matches("stop_reason"):
        return 1.0
    return 0.5


async def run_referee_family(module_source: str, entry: dict) -> tuple[dict, float]:
    result = await runner.run_child(
        "child_driver_referee.py",
        module_source,
        {"scripts": [s["script"] for s in entry["scripts"]]},
        wall_clock=120.0,
    )
    if not result.ok or result.payload is None:
        return {"skipped": result.failure or "child-failure"}, 0.0
    gate = result.payload["gate"]
    results = result.payload["results"]
    outcome = {"results": results, "gate": gate}
    expects = [s["expect"] for s in entry["scripts"]]
    if not all(gate.values()):
        return outcome, 0.0
    if not isinstance(results, list) or len(results) != len(expects):
        return outcome, 0.0
    credit = sum(_script_credit(g, w) for g, w in zip(results, expects))
    return outcome, credit / len(expects)


# ---- redaction family -------------------------------------------------------


def _declared_raw_secret_values(record: dict) -> list[str]:
    rows = record.get("secrets") or []
    values = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        raw = item.get("value")
        if isinstance(raw, str) and raw:
            values.append(raw)
    return values


def _contains_any_raw_secret(value: object, raw_values: list[str]) -> bool:
    if isinstance(value, str):
        return any(raw in value for raw in raw_values)
    if isinstance(value, list):
        return any(_contains_any_raw_secret(item, raw_values) for item in value)
    if isinstance(value, dict):
        return any(
            _contains_any_raw_secret(item, raw_values) for item in value.values()
        )
    return False


def _redaction_gate(results: object, entry: dict) -> dict[str, bool]:
    fixtures = entry["fixtures"]
    expectations = [p["expect"] for p in fixtures]
    if not isinstance(results, list) or len(results) != len(fixtures):
        return {
            "result_shape": False,
            "no_raw_secret_leaks": False,
            "all_exact": False,
        }

    result_shape = all(
        isinstance(result, dict) and "error" not in result for result in results
    )
    no_raw_secret_leaks = all(
        not _contains_any_raw_secret(
            result, _declared_raw_secret_values(fixture["record"])
        )
        for result, fixture in zip(results, fixtures)
    )
    try:
        all_exact = runner.match_fraction(results, expectations) == 1.0
    except (TypeError, ValueError):
        all_exact = False

    return {
        "result_shape": result_shape,
        "no_raw_secret_leaks": no_raw_secret_leaks,
        "all_exact": all_exact,
    }


async def run_redaction_family(module_source: str, entry: dict) -> tuple[dict, float]:
    result = await runner.run_child(
        "child_driver_redaction.py",
        module_source,
        [p["record"] for p in entry["fixtures"]],
        wall_clock=60.0,
    )
    if not result.ok or result.payload is None:
        return {"skipped": result.failure or "child-failure"}, 0.0
    results = result.payload.get("results")
    gate = _redaction_gate(results, entry)
    outcome = {"results": results if isinstance(results, list) else [], "gate": gate}
    return outcome, 1.0 if all(gate.values()) else 0.0


FAMILY_RUNNERS = {
    "parser-contract": run_parser_family,
    "rubric-contract": run_rubric_family,
    "rubric-repair": run_rubric_family,
    "referee-protocol": run_referee_family,
    "redaction-contract": run_redaction_family,
}
