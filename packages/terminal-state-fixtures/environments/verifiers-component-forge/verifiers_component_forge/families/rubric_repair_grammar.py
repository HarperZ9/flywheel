"""Fixture battery for the rubric-repair family.

The battery is the rubric-contract battery for the seed contract plus
repair-specific rows, added so every shipped mutation operator has at least
two fixtures that distinguish broken from reference behavior (one can then be
shown as the visible symptom while another stays hidden and scored), and so
per-func boundary rows (empty completion, case flips, whitespace pads, a
second length boundary, a negative ratio, a truthy-int flag) are present in
every battery regardless of which mutation shipped.

Expectations are never written here: the generator executes both the
reference and the broken module through the real verifiers machinery over
this battery, freezes the reference outputs, and derives kill flags from the
disagreements.
"""

from __future__ import annotations

from .rubric_contract import Contract
from .rubric_contract_grammar import _baseline_info, fixtures_for


def battery_for(contract: Contract) -> list[dict]:
    rows = fixtures_for(contract)
    vid = contract.variant_id
    answer = f"ans-{vid}"
    kinds = {c.kind: c for c in contract.criteria}

    def add(cell: str, completion: str, info_overrides: dict | None = None) -> None:
        info = dict(_baseline_info(contract))
        if info_overrides:
            info.update(info_overrides)
        rows.append(
            {
                "cell": cell,
                "prompt": f"repair probe for {vid}",
                "completion": completion,
                "answer": answer,
                "info": info,
            }
        )

    # A second excluded row, partially-strong, so exclusion mutations flip
    # more than the single base excluded-true row.
    add("excluded-true-partial", f"around {answer} padding", {"excluded": True})
    # Case and whitespace boundary rows (kill exact-casefold / exact-strip;
    # boundary coverage for every shipped instance regardless of operator).
    add("case-flip", answer.upper())
    add("case-flip-title", answer.capitalize())
    add("whitespace-pad", answer + "  ")
    add("whitespace-pad-leading", " " + answer)
    add("empty-completion", "")
    if "len_under" in kinds:
        n = kinds["len_under"].param
        assert isinstance(n, int)
        add("len-at-boundary-alt", "y" * n)
    if "info_ratio" in kinds:
        add("ratio-clamped-negative", answer, {kinds["info_ratio"].param: -0.4})
    if "info_flag" in kinds:
        add("flag-truthy-int", answer, {kinds["info_flag"].param: 2})
    return rows
