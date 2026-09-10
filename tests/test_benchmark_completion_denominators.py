"""Keep failures and unavailable assignments in the observed-pass denominator."""
import copy

import pytest

from harness.graded_metric_report import build_report, render_markdown, summarize_role
from scripts.benchmark_head_to_head import render_html, render_markdown as page_markdown, role_cells


def attempt(state="pass", *, launched=True, failure=""):
    return {"provider_role": "a", "oracle_state": state, "launched": launched,
            "blocked": not launched, "failure_class": failure, "metrics": {},
            "execution_state": "returned" if launched else "unavailable"}


def mixed_attempts():
    return [attempt(), attempt("fail"), attempt("not_run", failure="timeout"),
            attempt("not_run", failure="_MalformedAttempt"),
            attempt("not_run", launched=False)]


def test_all_assigned_attempts_stay_in_the_observed_pass_denominator():
    rows = mixed_attempts()
    before = copy.deepcopy(rows)
    summary = summarize_role("a", rows)
    assert summary["attempts"] == 5 and summary["oracle_pass"] == 1
    assert summary["pass_rate_all_attempts"] == 0.2
    assert summary["pass_rate"] == 0.5  # Existing conditional-quality field is stable.
    assert summary["readable_rate"] == 0.4 and summary["launch_rate"] == 0.8
    assert summary["unreadable_reasons"] == {
        "over the time budget": 1, "refused at the envelope": 1}
    assert rows == before


def test_adding_an_unreadable_attempt_changes_completion_not_conditional_quality():
    rows = mixed_attempts()
    baseline = summarize_role("a", rows)
    summary = summarize_role("a", rows + [attempt("not_run", failure="timeout")])
    assert summary["pass_rate_all_attempts"] == round(1 / 6, 4)
    assert summary["pass_rate_all_attempts"] < baseline["pass_rate_all_attempts"]
    assert summary["pass_rate"] == baseline["pass_rate"] == 0.5


@pytest.mark.parametrize("rows, expected", [
    ([], None), ([attempt("not_run", launched=False)], 0.0),
    ([attempt("not_run", failure="timeout")], 0.0), ([attempt("fail")], 0.0),
])
def test_empty_assignments_and_zero_observed_passes_remain_distinct(rows, expected):
    summary = summarize_role("a", rows)
    assert summary["pass_rate_all_attempts"] == expected
    if not rows or rows[0]["oracle_state"] != "fail":
        assert summary["pass_rate"] is None


def test_renderers_expose_both_pass_denominators_and_keep_unreadable_reasons():
    record = build_report(mixed_attempts())
    for text in (render_markdown(record), render_html(record), "\n".join(page_markdown(record))):
        assert "passed / all attempts" in text
        assert "passed / readable" in text
        assert "1/5 (20%)" in text and "1/2 (50%)" in text
        assert "unavailable" in text and "oracle" in text
    assert "over the time budget" in render_html(record)
    assert "refused at the envelope" in render_html(record)


def test_legacy_record_renders_counts_without_trusting_contradictory_stored_rates():
    summary = summarize_role("a", mixed_attempts())
    summary.pop("pass_rate_all_attempts", None)
    summary["pass_rate"] = 0.99
    summary["readable_rate"] = 0.99
    cells = {label: text for label, text, _ in role_cells(summary)}
    assert cells["passed / all attempts"] == "1/5 (20%)"
    assert cells["passed / readable"] == "1/2 (50%)"
    assert "99%" not in cells.values()


def test_no_readable_answer_keeps_the_conditional_pass_cell_unmeasured():
    summary = summarize_role("a", [attempt("not_run", launched=False)])
    cells = {label: (text, absent) for label, text, absent in role_cells(summary)}
    assert cells["passed / all attempts"] == ("0/1 (0%)", False)
    assert cells["passed / readable"] == ("not reported", True)


def test_generated_surfaces_identify_the_distinct_head_to_head_source():
    from scripts import build_benchmark_page as page
    surfaces = page.build()
    for text in (surfaces["site/benchmarks.html"], surfaces["docs/BENCHMARKS.md"], page.__doc__):
        assert "docs/benchmarks/report.json" in text
        assert "docs/benchmarks/graded-metrics.json" in text
        assert "offline suite" in text.lower() and "head-to-head" in text
