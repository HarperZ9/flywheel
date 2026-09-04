"""Falsifiers for the rollup that feeds the published charts.

A scorecard holds every graded measurement one attempt at a time. Nothing read
it, so the published surface could say which harness passed and never say by how
much or what the answer cost. This module is what turns those rows into numbers
a chart can carry, which makes its honest-null discipline load-bearing: a rate
computed over an empty denominator, or a cost total summed over the subset of
attempts whose provider happened to report one, becomes a bar on a public page.

Four of the five roles in the 2026-09-03 run report no cost at all. A total that
hides that reads as though the run was nearly free. So the tests below are
mostly about what the report refuses to say.
"""
import json

from harness.graded_metric_report import (DIRECTION, DOES_NOT_PROVE, build_report, load_scorecard,
                                          render_markdown, summarize_checker, summarize_role)
from scripts.run_graded_metric_report import main


def row(role, *, launched=True, state="pass", cost=None, latency=100.0, tokens=None,
        checker="evidence_bound_reporting/v1", evidence=None, task="agt-015"):
    metrics = {"latency_ms": latency, "resource_observation": {}, "usage": {}}
    if cost is not None:
        metrics["resource_observation"]["provider_reported_cost_usd"] = cost
    if tokens is not None:
        metrics["usage"]["aggregate"] = {"output_tokens": tokens}
    return {"provider_role": role, "task_id": task, "run_id": "run-1", "source_commit": "abc",
            "task_set_id": "set-1", "model_id": role + "-model", "launched": launched,
            "blocked": not launched, "execution_state": "returned" if launched else "unavailable",
            "oracle_state": state, "metrics": metrics,
            "oracle_evidence": {"checker_id": checker, "evidence": dict(evidence or {})}}


def test_a_rate_with_no_denominator_is_null_and_not_zero():
    """Nothing launched is not a pass rate of zero. It is an unmeasured one.

    Zero would draw a bar. Null draws nothing, which is what the run supports.
    """
    summary = summarize_role("local_14b", [row("local_14b", launched=False, state="not_run")])
    assert summary["launched"] == 0 and summary["scored"] == 0
    assert summary["launch_rate"] == 0.0
    assert summary["pass_rate"] is None
    assert summary["latency_ms_median"] is None


def test_a_role_whose_provider_reports_no_cost_says_so_rather_than_reporting_zero():
    """The Codex CLI and the Ollama endpoint state no cost. Free is a claim."""
    summary = summarize_role("codex_harness", [row("codex_harness"), row("codex_harness")])
    assert summary["cost_usd_total"] is None
    assert summary["cost_reported_attempts"] == 0
    assert summary["cost_coverage"] == 0.0
    assert summary["null_reasons"]["cost_usd_total"] == "provider_cost_unavailable"
    assert summary["null_reasons"]["cost_usd_per_scored_attempt"] == "provider_cost_unavailable"


def test_a_partly_costed_role_reports_the_total_but_refuses_the_per_attempt_figure():
    """The dangerous case, because a partial sum still looks whole.

    The total is what the provider actually stated and is kept, with the
    coverage beside it. Dividing it by every scored attempt would price the
    attempts that reported nothing at the rate of the ones that did.
    """
    summary = summarize_role("claude_code", [row("claude_code", cost=0.14), row("claude_code")])
    assert summary["cost_usd_total"] == 0.14
    assert summary["cost_reported_attempts"] == 1 and summary["cost_coverage"] == 0.5
    assert summary["cost_usd_per_scored_attempt"] is None
    assert summary["null_reasons"]["cost_usd_per_scored_attempt"] == "partial_cost_coverage"


def test_a_fully_costed_role_divides_by_what_it_actually_scored():
    rows = [row("claude_code", cost=0.10, tokens=40), row("claude_code", cost=0.30, tokens=60, state="fail")]
    summary = summarize_role("claude_code", rows)
    assert summary["cost_usd_total"] == 0.4 and summary["cost_coverage"] == 1.0
    assert summary["scored"] == 2 and summary["oracle_pass"] == 1
    assert summary["cost_usd_per_scored_attempt"] == 0.2
    assert summary["pass_rate"] == 0.5 and summary["output_tokens_total"] == 100
    assert summary["null_reasons"] == {}


def test_latency_percentiles_are_values_the_run_actually_observed():
    """Nearest-rank, so no reported latency is one no attempt took."""
    rows = [row("r", latency=value) for value in (10.0, 20.0, 30.0, 400.0)]
    summary = summarize_role("r", rows)
    assert summary["latency_ms_median"] in {20.0, 30.0}
    assert summary["latency_ms_p90"] == 400.0


def test_a_checker_keeps_each_role_denominator_instead_of_pooling_them():
    """A metric one role never reported must not be averaged into its column."""
    rows = [row("a", evidence={"evidence_bound_score": 0.8, "fabricated_measurements": 0}),
            row("a", evidence={"evidence_bound_score": 0.6, "fabricated_measurements": 2}),
            row("b", evidence={"evidence_bound_score": 0.5})]
    summary = summarize_checker("evidence_bound_reporting/v1", rows)
    by_name = {metric["metric"]: metric for metric in summary["metrics"]}
    scores = {entry["provider_role"]: entry for entry in by_name["evidence_bound_score"]["roles"]}
    assert scores["a"]["n"] == 2 and scores["a"]["mean"] == 0.7
    assert scores["b"]["n"] == 1 and scores["b"]["mean"] == 0.5
    fabricated = {entry["provider_role"]: entry
                  for entry in by_name["fabricated_measurements"]["roles"]}
    assert fabricated["b"]["n"] == 0 and fabricated["b"]["mean"] is None


def test_every_metric_a_chart_can_draw_declares_which_way_is_better():
    """A bar with no orientation is decoration. Unknown is allowed and is named."""
    rows = [row("a", evidence={"evidence_bound_score": 0.8, "invented_metric": 1.0})]
    summary = summarize_checker("evidence_bound_reporting/v1", rows)
    directions = {metric["metric"]: metric["direction"] for metric in summary["metrics"]}
    assert directions["evidence_bound_score"] == DIRECTION["evidence_bound_score"] == "higher"
    assert directions["invented_metric"] == "unknown"


def test_a_boolean_is_not_a_measurement():
    """True is an int in Python and would otherwise average into a mean of 1.0."""
    summary = summarize_checker("c", [row("a", evidence={"passed": True, "score": 0.5})])
    assert [metric["metric"] for metric in summary["metrics"]] == ["score"]


def test_only_a_scored_attempt_reaches_a_checker_column():
    """A malformed attempt has no graded numbers, which is not a score of zero."""
    rows = [row("a", state="malformed", evidence={"evidence_bound_score": 0.9}),
            row("a", state="pass", evidence={"evidence_bound_score": 0.4})]
    record = build_report(rows)
    assert record["counts"]["scored"] == 1
    entry = record["checkers"][0]["metrics"][0]["roles"][0]
    assert entry["n"] == 1 and entry["mean"] == 0.4


def test_the_record_carries_what_it_cannot_support():
    record = build_report([row("a")])
    assert record["does_not_prove"] == DOES_NOT_PROVE
    assert record["schema"] == "flywheel.graded_metric_report/v1"
    assert record["run_ids"] == ["run-1"] and record["source_commits"] == ["abc"]


def test_a_missing_number_renders_as_a_named_absence_not_a_blank_cell():
    table = render_markdown(build_report([row("a")]))
    assert "not reported" in table
    assert "## What this does not prove" in table


def _write(tmp_path, rows, name="scorecard.json"):
    path = tmp_path / name
    path.write_text(json.dumps({"schema": "harness.cross-harness-task-scorecard/v1", "rows": rows}),
                    encoding="utf-8")
    return str(path)


def test_the_reader_refuses_a_document_with_no_rows(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"schema": "x"}), encoding="utf-8")
    try:
        load_scorecard(path)
    except ValueError as exc:
        assert "no rows" in str(exc)
    else:
        raise AssertionError("a document with no rows was accepted")


def test_the_script_pools_the_scorecards_it_is_given(tmp_path):
    first = _write(tmp_path, [row("a", cost=0.1)], "one.json")
    second = _write(tmp_path, [row("b", cost=0.2)], "two.json")
    out = tmp_path / "report.json"
    assert main(["--scorecard", first, "--scorecard", second, "--out", str(out),
                 "--markdown-out", str(tmp_path / "report.md"), "--quiet"]) == 0
    record = json.loads(out.read_text(encoding="utf-8"))
    assert [entry["provider_role"] for entry in record["roles"]] == ["a", "b"]
    assert record["scorecard_paths"] == [first, second]
    assert (tmp_path / "report.md").read_text(encoding="utf-8").startswith("# Graded metric report")


def test_the_script_says_so_instead_of_reporting_on_nothing(capsys):
    assert main([]) == 2
    assert "no scorecard given" in capsys.readouterr().err


def test_a_floor_below_what_was_scored_fails_the_run(tmp_path, capsys):
    path = _write(tmp_path, [row("a")])
    assert main(["--scorecard", path, "--min-scored", "5", "--quiet"]) == 1
    assert "floor is 5" in capsys.readouterr().err


def test_partial_cost_coverage_can_be_made_to_fail_rather_than_read_as_a_total(tmp_path, capsys):
    path = _write(tmp_path, [row("a", cost=0.1), row("a")])
    assert main(["--scorecard", path, "--quiet"]) == 0
    assert main(["--scorecard", path, "--require-cost-coverage", "--quiet"]) == 1
    assert "partial cost coverage: a" in capsys.readouterr().err
