"""Fixture grammar for the rubric-contract family.

Each contract gets a deterministic fixture table aimed at every criterion's
branch structure plus the contract's rule seams: both sides of each boolean
criterion, the clamp and both malformed shapes for info criteria, the
exclusion flag under contracts that honor it AND contracts that must ignore
it, the negative-weight firing row, and a diagnostic-only pair whose weighted
outcome is identical while the zero-weight metric differs.

Expectations are never written here: the generator executes the contract's
reference module through the real verifiers machinery over these fixtures and
freezes what comes back.
"""

from __future__ import annotations

from .rubric_contract import Contract


def _baseline_info(contract: Contract) -> dict:
    info: dict = {}
    kinds = {c.kind: c for c in contract.criteria}
    if "info_ratio" in kinds:
        info[kinds["info_ratio"].param] = 0.8
    if "info_flag" in kinds:
        info[kinds["info_flag"].param] = True
    return info


def fixtures_for(contract: Contract) -> list[dict]:
    vid = contract.variant_id
    answer = f"ans-{vid}"
    strong = answer  # exact hit, short, starts lowercase ("a")
    kinds = {c.kind: c for c in contract.criteria}
    rows: list[dict] = []

    def add(
        cell: str,
        completion: str,
        info_overrides: dict | None = None,
        drop_keys: tuple[str, ...] = (),
    ) -> None:
        info = dict(_baseline_info(contract))
        for k in drop_keys:
            info.pop(k, None)
        if info_overrides:
            info.update(info_overrides)
        rows.append(
            {
                "cell": cell,
                "prompt": f"task for {vid}",
                "completion": completion,
                "answer": answer,
                "info": info,
            }
        )

    # Global rows.
    add("all-strong", strong)
    add("all-weak", "zz")  # misses exact/contains, lowercase, very short
    add("excluded-true", strong, {"excluded": True})
    add("excluded-false", strong, {"excluded": False})

    # Per-kind branch rows.
    if "exact" in kinds:
        add("exact-miss-contains-hit", f"around {answer} padding")
    if "contains" in kinds and "exact" not in kinds:
        add("contains-hit", f"around {answer} padding")
        add("contains-miss", "unrelated words entirely")
    if "starts_upper" in kinds:
        add("upper-hit", "Answer shaped but wrong")
    if "len_under" in kinds:
        n = kinds["len_under"].param
        assert isinstance(n, int)
        at = "x" * n  # exactly N chars: boundary HIT
        over = "x" * (n + 1)  # one over: MISS
        add("len-at-boundary", at)
        add("len-one-over", over)
    if "info_ratio" in kinds:
        key = kinds["info_ratio"].param
        assert isinstance(key, str)
        add("ratio-clamped", strong, {key: 1.7})
        add("ratio-malformed", strong, {key: "high"})
        add("ratio-missing", strong, drop_keys=(key,))
    if "info_flag" in kinds:
        key = kinds["info_flag"].param
        assert isinstance(key, str)
        add("flag-false", strong, {key: 0})
        add("flag-truthy-string", strong, {key: "yes"})
        add("flag-missing", strong, drop_keys=(key,))

    # Negative-weight firing row: the second criterion is the one negated.
    # A row where it scores 1.0 makes the reward DROP under negative
    # contracts; the generator freezes whichever value the reference yields.
    add(
        "second-criterion-fires",
        f"around {answer} padding"
        if contract.criteria[1].kind == "contains"
        else strong,
    )

    # Diagnostic-only pair: identical weighted behavior, different lengths.
    add("diag-pair-short", "zz")
    add("diag-pair-long", "zz" + " pad" * 6)
    return rows


def worked_for(contract: Contract) -> list[dict]:
    """Two display rows for the prompt, never scored. Payloads use the
    ``example`` marker, which fixtures_for never emits."""
    answer = "example-answer"
    base = dict(_baseline_info(contract))
    return [
        {
            "cell": "worked-strong",
            "prompt": "worked example",
            "completion": answer,
            "answer": answer,
            "info": base,
        },
        {
            "cell": "worked-weak",
            "prompt": "worked example",
            "completion": "Example of a longer, unrelated reply for display.",
            "answer": answer,
            "info": {},
        },
    ]
