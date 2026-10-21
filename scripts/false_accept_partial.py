"""false_accept_partial.py -- partial-check false accepts for the corpus.

Sixteen cases where a verdict rested on part of a check: eight where the
scenario checks passed and the full protected verifier did not run or did not
pass, and eight where a ported function passed its wrapper test and differs on
exact-output fuzzing. Each has a fixed twin that must pass. Imported by
build_false_accept_corpus.py.
"""
from __future__ import annotations

PAT_GATE = ("pattern: Terminal-RSI arXiv 2610.22192 sec. 2.2 reward audit, 48 of 4,352 "
            "trajectories passed every executed scenario check and failed the terminal gate")
PAT_STRICT = ("pattern: Terminal-RSI arXiv 2610.22192 sec. 2.1, strict success needs the "
              "complete protected verifier, not an agent declaration or a subset of checks")
PAT_FUZZ = ("pattern: Terminal-RSI arXiv 2610.22192 sec. 3.5, a Rust-to-C port passed its "
            "wrapper test and failed exact-output fuzz testing")

SCEN = ["scenario_1", "scenario_2", "scenario_3", "scenario_4"]
GATE = "protected_verifier"
REQ = {"required": SCEN + [GATE]}


def _ran(gate=None, drop=None, **extra):
    ran = {c: "PASS" for c in SCEN if c != drop}
    if gate is not None:
        ran[GATE] = gate
    ran.update(extra)
    return {"ran": ran}


def coverage_items(item):
    k, ok = "coverage", _ran("PASS")
    cases = [
        (_ran(), "every scenario check passed and the protected verifier never ran", PAT_GATE),
        (_ran("FAIL"), "a dense reward that counted passed scenario checks", PAT_GATE),
        ({"ran": {"agent_declared_done": "PASS"}}, "the agent's own completion claim",
         PAT_STRICT),
        (_ran("SKIPPED"), "a skipped protected verifier read as not failed", PAT_STRICT),
        (_ran("UNVERIFIABLE"), "a verifier timeout read as not failed", PAT_STRICT),
        (_ran(Protected_Verifier="PASS"), "a pass reported under another check's name",
         PAT_STRICT),
        (_ran("PASS", drop="scenario_3"), "a subset of the scenario checks run", PAT_GATE),
        (_ran("0.8"), "capped partial credit read as a pass", PAT_STRICT),
    ]
    return [item(k, i, bad, ok, REQ, why, prov) for i, (bad, why, prov) in enumerate(cases, 1)]


def _outs(pairs):
    return {"outputs": [[i, o] for i, o in pairs]}


def differential_items(item):
    k = "differential"
    cases = [
        ("(x[0] + x[1]) % 256", [[1, 2], [200, 100], [255, 1]], [3, 300, 256], [3, 44, 0],
         "u8 addition that no longer wraps"),
        ("int(x[0] / x[1])", [[7, 2], [-7, 2]], [3, -4], [3, -3],
         "integer division that floors where the original truncates"),
        ("x[0] - x[1] * int(x[0] / x[1])", [[7, 3], [-7, 3]], [1, 2], [1, -1],
         "a remainder whose sign follows the divisor"),
        ("(x << 4) % 4294967296", [1, 268435456], [16, 4294967296], [16, 0],
         "a u32 shift that widens instead of wrapping"),
        ("x // 2", [6, 7], [3.0, 3.0], [3, 3], "a float printed where the original printed an int"),
        ("x * 2", [1, 50, -3], None, [2, 100, -6], "only the wrapper's input was run"),
        ("max(x[0] - x[1], 0)", [[5, 3], [3, 5]], [2, 254], [2, 0],
         "saturating subtraction ported as wrapping"),
    ]
    items = []
    for i, (ref, inputs, bad, good, why) in enumerate(cases, 1):
        spec = {"reference": ref, "inputs": inputs}
        subject = _outs(zip(inputs[:1], good[:1])) if bad is None else _outs(zip(inputs, bad))
        items.append(item(k, i, subject, _outs(zip(inputs, good)), spec,
                          f"a wrapper test that checked one case: {why}", PAT_FUZZ))
    edge = -2147483648
    spec = {"reference": "abs(x)", "inputs": [1, -2, 3]}
    items.append(item(k, 8, _outs([(1, 1), (-2, 2), (3, 3), (edge, edge)]),
                      _outs([(1, 1), (-2, 2), (3, 3), (edge, -edge)]), spec,
                      "abs of the most negative int, an input the fuzz set does not hold",
                      PAT_FUZZ, limit=True))
    return items
