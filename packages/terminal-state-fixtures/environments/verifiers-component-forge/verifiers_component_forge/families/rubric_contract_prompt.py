"""Prose renderer for rubric-contract variants.

Renders the scoring contract from the FROZEN contract dict (names, kinds,
weights, rules) plus the frozen worked rows, so eval-time rendering never
re-executes the reference. Full-precision expectations live in the frozen
file; the worked rows are displayed rounded and say so.
"""

from __future__ import annotations

import json

_KIND_PROSE = {
    "exact": "1.0 when the completion equals the answer exactly, else 0.0.",
    "contains": (
        "1.0 when the answer appears as a substring of the completion, else 0.0."
    ),
    "len_under": (
        "1.0 when len(completion) <= {param}, else 0.0. The boundary counts: "
        "exactly {param} characters scores 1.0."
    ),
    "starts_upper": (
        "1.0 when the completion's first character is uppercase "
        "(str.isupper on completion[:1]), else 0.0. Empty completion: 0.0."
    ),
    "info_ratio": (
        "float(info[{param!r}]) clamped into [0.0, 1.0]. A missing key or a "
        "value float() rejects falls under the ERROR RULE."
    ),
    "info_flag": (
        "1.0 when bool(info[{param!r}]) is true, else 0.0. A missing key "
        "falls under the ERROR RULE."
    ),
    "len_metric": "float(len(completion)). Diagnostic only.",
    "word_metric": "float(len(completion.split())). Diagnostic only.",
}


def _criterion_prose(name: str, kind: str, param: object) -> str:
    text = _KIND_PROSE[kind]
    if "{param" in text:
        text = text.replace("{param!r}", repr(param)).replace("{param}", str(param))
    return f"`{name}`: {text}"


DELIVERABLE_PROSE = (
    "Your module must define `load_environment(**kwargs)` returning a "
    "`vf.SingleTurnEnv` whose `vf.Rubric` implements this contract "
    "through the library's own reward-function machinery: "
    "`vf.Rubric(funcs=[...], weights=[...])`, one function per criterion, "
    "function `__name__`s exactly equal to the criterion names, in the "
    "contract's order, with exactly the contract's weight vector. Do not "
    "replace or override the rubric's scoring loop. A one-row stub "
    'dataset (`[{"question": "stub", "answer": "stub"}]`) is the blessed '
    "minimal dataset. Reward functions receive `completion`, `answer`, "
    "and `info` as keyword arguments; `completion` is a plain string."
)

EMISSION_LINES = (
    "## Emission protocol",
    "",
    (
        "Reply with your complete module in a single ```python code fence. "
        "Extraction takes everything between the LAST ```python opener and "
        "the LAST ``` in your reply. The module must import nothing beyond "
        "the Python standard library, `verifiers`, and `datasets`."
    ),
)


def contract_lines(contract: dict) -> list[str]:
    """The criteria table and rules sections, shared verbatim by the
    rubric-contract prompt and the rubric-repair REWARD.md."""
    lines: list[str] = []
    a = lines.append
    a("## Criteria, in order")
    a("")
    for (name, kind, param), weight in zip(contract["kinds"], contract["weights"]):
        a(f"- weight {weight!r} -- " + _criterion_prose(name, kind, param))
    a("")
    a("## Rules")
    a("")
    a(
        "- AGGREGATION: the reward is the raw weighted sum of the criterion "
        "values with the weights above. Do NOT normalize the weights, do NOT "
        "rescale the sum, and do NOT fold zero-weight criteria into any "
        "denominator. Negative weights, where present, subtract."
    )
    a(
        "- ERROR RULE: a criterion whose info key is missing or malformed "
        "evaluates to 0.0. Never raise."
    )
    if contract["exclusion"]:
        a(
            '- EXCLUSION RULE: when `info["excluded"]` is exactly `True`, '
            "every WEIGHTED criterion evaluates to 0.0. Zero-weight "
            "diagnostic criteria still compute and report their real value."
        )
    else:
        a(
            '- The key `"excluded"`, if present in info, is ordinary data. '
            "Ignore it; no criterion changes behavior because of it."
        )
    return lines


def render_prompt(contract: dict, worked: list[dict]) -> str:
    lines: list[str] = []
    a = lines.append
    a(
        "Write a Python module implementing EXACTLY the scoring contract "
        "below as a verifiers environment."
    )
    a("")
    a("## Deliverable")
    a("")
    a(DELIVERABLE_PROSE)
    a("")
    lines += contract_lines(contract)
    a("")
    a("## Worked rows (illustrative only; never scored; values rounded to 4dp)")
    a("")
    for row in worked:
        fx = row["fixture"]
        expect = row["expect"]
        metrics = {k: round(v, 4) for k, v in expect["metrics"].items()}
        a(
            f"completion={fx['completion']!r}, answer={fx['answer']!r}, "
            f"info={json.dumps(fx['info'], sort_keys=True)}"
        )
        a(
            f"-> reward {round(expect['reward'], 4)!r}, "
            f"metrics {json.dumps(metrics, sort_keys=True)}"
        )
        a("")
    lines += EMISSION_LINES
    return "\n".join(lines)
