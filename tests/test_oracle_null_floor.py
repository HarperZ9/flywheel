"""Measure the oracles against candidates that did not do the task.

A pass rate only means something if something can fail. These tests drive every
configured checker with three ways of not answering and record what each one
scores, so "the oracles discriminate" is a measurement in this suite rather than
a claim in a document.

The measurement found a breach. `documentation_maintenance/v1` scores a
submission that hands its own fixture back, because every comparison it makes is
report-against-fixture. The table below records that rather than asserting it
away, and `documentation_maintenance/v2` is the checker written to close it.
"""
from __future__ import annotations

import json

import pytest

from harness.cross_harness_null_adapters import (
    BREACHED, HELD, MECHANICAL, PREAMBLE_REASONS, REJECTING, SCHEMA, STRATEGIES,
    build_null_floor_report, echo_report, hollow, rejected_at, write_null_submission,
)
from harness.cross_harness_oracles import OracleContext, evaluate_task_oracle
from test_cross_harness_oracles import TASKS, _case
from test_oracle_documentation_v2 import CHECKER_ID as DOCS_V2, case_v2

DOCS_V1 = "documentation_maintenance/v1"
CHECKERS = (*TASKS, DOCS_V2)

# The floor as measured, one row per (checker, strategy). The first value is the
# state the oracle returned and the second is where the candidate was thrown
# out. Pinning it means a checker that gets weaker fails here instead of quietly
# raising a score.
FLOOR = {
    ("index_fallback_integrity/v1", "empty"): ("malformed", "preamble"),
    ("index_fallback_integrity/v1", "shape"): ("fail", "checker"),
    ("index_fallback_integrity/v1", "echo"): ("fail", "checker"),
    ("shared_task_artifact/v1", "empty"): ("malformed", "preamble"),
    ("shared_task_artifact/v1", "shape"): ("malformed", "checker"),
    ("shared_task_artifact/v1", "echo"): ("malformed", "checker"),
    ("paired_friction/v1", "empty"): ("malformed", "preamble"),
    ("paired_friction/v1", "shape"): ("fail", "checker"),
    ("paired_friction/v1", "echo"): ("fail", "checker"),
    (DOCS_V1, "empty"): ("malformed", "preamble"),
    (DOCS_V1, "shape"): ("fail", "checker"),
    (DOCS_V1, "echo"): ("pass", "none"),
    (DOCS_V2, "empty"): ("malformed", "preamble"),
    (DOCS_V2, "shape"): ("fail", "checker"),
    (DOCS_V2, "echo"): ("fail", "checker"),
}

# The single (checker, strategy) pair the floor does not hold for.
KNOWN_BREACH = (DOCS_V1, "echo")


def _build(tmp_path, checker):
    return case_v2(tmp_path) if checker == DOCS_V2 else _case(tmp_path, checker)


def _null_row(tmp_path, checker, strategy):
    """The good case with only the submission swapped, scored and recorded."""
    context, report, fixture = _build(tmp_path, checker)
    submission = write_null_submission(
        context.raw_output_path.parent, strategy=strategy, task_id=context.task_id,
        template=report, fixture=fixture, expected_artifacts=tuple(context.artifact_paths))
    swapped = OracleContext(context.task_id, context.oracle_spec, submission.raw_output_path,
                            submission.artifact_paths, context.expected_input_sha256s,
                            context.scorecard_core)
    result = evaluate_task_oracle(swapped)
    reason = str((result.evidence or {}).get("reason", ""))
    return {"checker_id": checker, "strategy": strategy, "oracle_state": result.state,
            "failure_codes": list(result.failure_codes), "reason": reason,
            "rejected_at": rejected_at(result.failure_codes, reason),
            "rejected": result.state in REJECTING}


@pytest.mark.parametrize("checker", CHECKERS)
def test_the_good_case_still_passes(tmp_path, checker):
    """The control. Without it a held floor could mean the setup is broken for
    every candidate, which would prove nothing about the checker."""
    context, _, _ = _build(tmp_path, checker)
    assert evaluate_task_oracle(context).state == "pass"


@pytest.mark.parametrize("checker, strategy", sorted(FLOOR))
def test_each_null_candidate_scores_what_the_table_records(tmp_path, checker, strategy):
    row = _null_row(tmp_path, checker, strategy)
    measured = (row["oracle_state"], row["rejected_at"])
    assert measured == FLOOR[(checker, strategy)], (
        f"{checker} scored the {strategy} candidate {measured}, "
        f"codes {row['failure_codes']}")


@pytest.mark.parametrize("checker, strategy", sorted(set(FLOOR) - {KNOWN_BREACH}))
def test_every_pair_but_the_known_breach_rejects(tmp_path, checker, strategy):
    row = _null_row(tmp_path, checker, strategy)
    assert row["oracle_state"] != "pass", (
        f"{checker} passed the {strategy} null candidate: the checker is easier "
        f"than its own inputs")
    assert row["rejected"]


def test_the_breach_is_real_and_v2_is_what_closes_it(tmp_path):
    """Same task, same fixture, same submission. Only the checker differs."""
    breached = _null_row(tmp_path / "v1", *KNOWN_BREACH)
    closed = _null_row(tmp_path / "v2", DOCS_V2, KNOWN_BREACH[1])
    assert breached["oracle_state"] == "pass" and breached["failure_codes"] == []
    assert closed["failure_codes"] == ["surface_digest_missing"]


def test_the_floor_report_carries_its_denominator_and_names_the_breach(tmp_path):
    rows = [_null_row(tmp_path / checker.replace("/", "-") / strategy, checker, strategy)
            for checker, strategy in sorted(FLOOR)]
    report = build_null_floor_report(rows, run_id="floor-test")
    assert report["schema"] == SCHEMA
    assert report["verdict"] == BREACHED
    assert report["breaches"] == [{"checker_id": DOCS_V1, "strategy": "echo",
                                   "oracle_state": "pass"}]
    assert report["denominator"] == {
        "candidates": len(FLOOR), "checkers": len(CHECKERS),
        "strategies": len(STRATEGIES), "checkers_reached": len(CHECKERS)}
    # Every checker was reached by at least one candidate, so no row in the
    # table is a rejection the shared preamble made on the checker's behalf.
    assert report["checkers_never_reached"] == []
    assert len(report["rows_sha256"]) == 64
    assert len(report["does_not_prove"]) == 4


def test_a_breach_is_named_rather_than_averaged_away():
    """A floor that cannot report failure is not a floor."""
    rows = [{"checker_id": "a/v1", "strategy": "shape", "oracle_state": "pass",
             "failure_codes": [], "rejected_at": "none", "rejected": False},
            {"checker_id": "a/v1", "strategy": "empty", "oracle_state": "malformed",
             "failure_codes": ["json_invalid"], "rejected_at": "checker", "rejected": True}]
    report = build_null_floor_report(rows)
    assert report["verdict"] == BREACHED
    assert report["breaches"] == [{"checker_id": "a/v1", "strategy": "shape",
                                   "oracle_state": "pass"}]
    assert report["denominator"]["candidates"] == 2


def test_a_checker_the_preamble_ate_is_not_counted_as_measured():
    """Rejecting every candidate before the checker runs is not a held floor.

    Reporting HELD there would credit the envelope check with discrimination the
    checker was never asked to show.
    """
    rows = [{"checker_id": "b/v1", "strategy": strategy, "oracle_state": "malformed",
             "failure_codes": ["json_invalid"], "rejected_at": "preamble", "rejected": True}
            for strategy in STRATEGIES]
    report = build_null_floor_report(rows)
    assert report["verdict"] == HELD
    assert report["checkers_never_reached"] == ["b/v1"]
    assert report["denominator"]["checkers_reached"] == 0


def test_the_stage_comes_from_the_reason_when_the_code_is_ambiguous():
    """`json_invalid` is emitted by the preamble and by a raising checker alike.

    Reading codes alone made `shared_task_artifact/v1` look unreachable when its
    checker had in fact run and rejected the candidate.
    """
    assert rejected_at(["json_invalid"], "raw_output_invalid") == "preamble"
    assert rejected_at(["json_invalid"], "raw_prompt_sha256_type_invalid") == "checker"
    assert rejected_at(["json_invalid"]) == "preamble"
    assert rejected_at([]) == "none"
    assert rejected_at(["surface_set_mismatch"]) == "checker"
    assert "response_envelope_invalid" in PREAMBLE_REASONS


def test_hollow_keeps_the_type_and_drops_the_content():
    assert hollow(True) is False and hollow(False) is False
    # bool before int matters: True is an int, and returning 0 for it would
    # change the type the checker sees.
    assert hollow(7) == 0 and hollow(1.5) == 0
    assert hollow("answer") == "" and hollow(["a"]) == [] and hollow({"k": 1}) == {}
    assert hollow(None) is None


def test_echo_returns_the_fixture_and_invents_nothing():
    template = {"task_id": "agt-001", "input_sha256s": {"f.json": "a" * 64},
                "events": [{"event_id": "e1"}], "verdict": "answered", "count": 3}
    fixture = {"events": [{"event_id": "e9", "type": "mcp_call"}]}
    out = echo_report(template, fixture)
    assert out["events"] == fixture["events"]
    # Mechanical fields survive because a provider derives them from its inputs.
    assert all(out[key] == template[key] for key in MECHANICAL if key in template)
    # A field the fixture never names is emptied, not guessed.
    assert out["verdict"] == "" and out["count"] == 0
    assert set(out) == set(template)
    # Echoing must not alias the fixture, or a later checker would score a
    # mutation the candidate never made.
    out["events"][0]["event_id"] = "mutated"
    assert fixture["events"][0]["event_id"] == "e9"


def test_the_strategies_write_distinguishable_submissions(tmp_path):
    template = {"task_id": "agt-001", "input_sha256s": {}, "events": [{"event_id": "e1"}]}
    written = {}
    for strategy in STRATEGIES:
        submission = write_null_submission(tmp_path / strategy, strategy=strategy,
                                           task_id="agt-001", template=template,
                                           fixture={"events": [{"event_id": "e9"}]})
        written[strategy] = submission.artifact_paths["report.json"].read_text(encoding="utf-8")
    assert written["empty"] == ""
    assert json.loads(written["shape"])["events"] == []
    assert json.loads(written["echo"])["events"] == [{"event_id": "e9"}]
    assert len(set(written.values())) == len(STRATEGIES)

    with pytest.raises(ValueError, match="unknown strategy"):
        write_null_submission(tmp_path / "x", strategy="cheat", task_id="t",
                              template=template, fixture={})
    with pytest.raises(ValueError, match="exactly one json"):
        write_null_submission(tmp_path / "y", strategy="shape", task_id="t",
                              template=template, fixture={},
                              expected_artifacts=("report.json",))


def test_the_front_controller_delegates_the_subcommand():
    """The floor is reachable through the one dispatcher, not only as a script."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    from run_harness_cli import build_command, build_manifest, build_parser

    args = build_parser().parse_args(["null-floor", "--fail-on-breach", "--out", "x.json"])
    command = build_command(args, repo_root=Path("."))
    assert command[1] == "scripts/run_null_floor.py"
    assert "--fail-on-breach" in command and "--out" in command
    # An unset optional flag is omitted rather than passed empty.
    assert "--markdown-out" not in command

    entry = next(row for row in build_manifest()["commands"] if row["name"] == "null-floor")
    assert entry["delegates_to"] == "scripts/run_null_floor.py"
    assert entry["schemas"] == [SCHEMA]
    assert "tests/test_oracle_null_floor.py" in entry["recommended_validation_slice"]
