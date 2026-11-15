"""Oracle soundness for the rubric-contract family.

Hand-derived arithmetic rows computed with pencil against specific frozen
fixtures (independent of the generator); structural invariants over the
frozen file; and the constant-1.0 floor: a module with the RIGHT names and
weights whose every criterion returns 1.0 passes the structural gate and
still fails the fixture battery, pinned as a ceiling."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from verifiers_component_forge.families.rubric_contract import (
    all_contracts,
    reference_module_source,
)
from verifiers_component_forge.harness import runner

DATA = (
    Path(__file__).resolve().parents[1]
    / "verifiers_component_forge"
    / "data"
    / "rubric_contract.json"
)


def _frozen() -> dict:
    return json.loads(DATA.read_text(encoding="utf-8"))


def _fixture(entry: dict, cell: str) -> dict:
    return next(p for p in entry["fixtures"] if p["cell"] == cell)


# ---- hand-derived arithmetic ------------------------------------------------
# Table 0: exact_match (0.7), brevity len<=24 (0.3), length_chars (0.0).
# answer for rc-00-excl0-neg0 is "ans-rc-00-excl0-neg0": 20 chars, under 24.


def test_all_strong_row_by_hand():
    entry = _frozen()["rc-00-excl0-neg0"]
    row = _fixture(entry, "all-strong")
    assert len(row["fixture"]["completion"]) == 20
    assert row["expect"]["reward"] == 1.0  # 0.7*1 + 0.3*1 + 0.0*20
    assert row["expect"]["metrics"] == {
        "exact_match": 1.0,
        "brevity": 1.0,
        "length_chars": 20.0,
    }


def test_negative_weight_subtracts_by_hand():
    # rc-00-excl0-neg1 negates brevity: 0.7*1 + (-0.3)*1 = 0.4 (approx).
    entry = _frozen()["rc-00-excl0-neg1"]
    row = _fixture(entry, "all-strong")
    assert abs(row["expect"]["reward"] - 0.4) < 1e-9


def test_exclusion_zeroes_weighted_but_not_diagnostics_by_hand():
    excl = _frozen()["rc-00-excl1-neg0"]
    row = _fixture(excl, "excluded-true")
    assert row["expect"]["reward"] == 0.0
    assert row["expect"]["metrics"]["exact_match"] == 0.0
    assert row["expect"]["metrics"]["length_chars"] == 20.0  # diagnostic real

    # Under a contract WITHOUT the rule, the flag is ignored entirely.
    plain = _frozen()["rc-00-excl0-neg0"]
    row2 = _fixture(plain, "excluded-true")
    assert row2["expect"]["reward"] == 1.0


def test_boundary_and_clamp_and_error_rows_by_hand():
    # Table 0 brevity boundary: exactly 24 chars hits, 25 misses.
    entry = _frozen()["rc-00-excl0-neg0"]
    at = _fixture(entry, "len-at-boundary")
    over = _fixture(entry, "len-one-over")
    assert at["expect"]["metrics"]["brevity"] == 1.0
    assert over["expect"]["metrics"]["brevity"] == 0.0
    # exact misses on both (completion is xxxx...), so reward = 0.3*brevity.
    assert abs(at["expect"]["reward"] - 0.3) < 1e-9
    assert over["expect"]["reward"] == 0.0

    # Table 1: contains (0.6), cited_confidence ratio (0.4), word_count (0.0).
    e2 = _frozen()["rc-01-excl0-neg0"]
    clamped = _fixture(e2, "ratio-clamped")  # 1.7 clamps to 1.0
    assert clamped["expect"]["metrics"]["cited_confidence"] == 1.0
    malformed = _fixture(e2, "ratio-malformed")  # "high" -> error rule -> 0.0
    assert malformed["expect"]["metrics"]["cited_confidence"] == 0.0
    missing = _fixture(e2, "ratio-missing")
    assert missing["expect"]["metrics"]["cited_confidence"] == 0.0


def test_flag_truthiness_by_hand():
    # Table 2: exact (0.8), used_tool flag (0.2), length_chars (0.0).
    entry = _frozen()["rc-02-excl0-neg0"]
    assert (
        _fixture(entry, "flag-truthy-string")["expect"]["metrics"]["used_tool"] == 1.0
    )
    assert _fixture(entry, "flag-false")["expect"]["metrics"]["used_tool"] == 0.0
    assert _fixture(entry, "flag-missing")["expect"]["metrics"]["used_tool"] == 0.0


# ---- frozen-file invariants -------------------------------------------------


def test_frozen_structure_and_negative_rewards_exist():
    data = _frozen()
    assert len(data) == 96
    any_negative = False
    for vid, entry in data.items():
        names = entry["contract"]["names"]
        # Table 3 (starts_upper + exact + diagnostic) bottoms out at 9
        # fixtures: no boundary or info-shape cells apply to its kinds.
        assert len(entry["fixtures"]) >= 9, vid
        assert len(entry["worked"]) == 2, vid
        for row in entry["fixtures"] + entry["worked"]:
            assert set(row["expect"]["metrics"].keys()) == set(names), vid
        for row in entry["worked"]:
            assert (
                "example" in row["fixture"]["answer"]
                or "Example" in row["fixture"]["completion"]
            )
        if any(p["expect"]["reward"] < 0 for p in entry["fixtures"]):
            any_negative = True
    assert any_negative, "no negative-weight fixture ever fires"


def test_frozen_matches_regeneration():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "generation"))
    import generate

    regenerated = generate._dumps(generate.build_rubric_contract())
    assert regenerated == DATA.read_text(encoding="utf-8")


# ---- the constant-1.0 floor -------------------------------------------------


def test_constant_rubric_passes_gate_but_fails_fixtures():
    contract = next(c for c in all_contracts() if c.variant_id == "rc-00-excl1-neg0")
    source = reference_module_source(contract)
    # Same names, same weights, every criterion body replaced with 1.0.
    constant = source
    for name in [c.name for c in contract.criteria]:
        head = f"def {name}(completion, answer, info, **kwargs):"
        i = constant.index(head)
        j = constant.index("\n\n", i)
        constant = constant[:i] + head + "\n    return 1.0" + constant[j:]
    entry = _frozen()[contract.variant_id]
    result = asyncio.run(
        runner.run_child(
            "child_driver_rubric.py",
            constant,
            {
                "contract": {
                    "names": entry["contract"]["names"],
                    "weights": entry["contract"]["weights"],
                },
                "fixtures": [p["fixture"] for p in entry["fixtures"]],
            },
            wall_clock=90.0,
        )
    )
    assert result.ok, (result.failure, result.stderr_tail)
    assert all(result.payload["gate"].values())  # names and weights are right
    score = runner.match_fraction(
        result.payload["results"],
        [p["expect"] for p in entry["fixtures"]],
    )
    # Measured 0.0-0.2 territory at freeze time; pinned with margin.
    assert score < 0.35, f"constant-1.0 rubric scored {score}"
