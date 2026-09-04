"""Falsifiers for the head-to-head section of the published benchmark page.

This section is the one a reader arrives for, because it is the only place the
surface compares Flywheel to the harness they already use. That makes every
missing number dangerous: an absent cost drawn as a total, or an unmeasured
rate drawn as a zero bar, is a comparison claim the run does not support.

So most of what follows checks that an absence stays visible as an absence.
"""
from scripts.benchmark_head_to_head import (ABSENT, HATCH_KEY, NOT_RUN, render_html,
                                            render_markdown, role_cells)


def role(name, **over):
    base = {"provider_role": name, "attempts": 7, "launched": 7, "blocked": 0, "returned": 7,
            "scored": 5, "oracle_pass": 3, "launch_rate": 1.0, "readable_rate": 0.7143,
            "pass_rate": 0.6, "latency_ms_median": 4200.0, "latency_ms_p90": 9000.0,
            "cost_usd_total": 0.14, "cost_reported_attempts": 7, "cost_coverage": 1.0,
            "cost_usd_per_scored_attempt": 0.028, "output_tokens_total": 900,
            "null_reasons": {}, "models_observed": [name + "-model"]}
    base.update(over)
    return base


def metric(name, direction="higher", means=(0.8, 0.5)):
    return {"metric": name, "direction": direction,
            "roles": [{"provider_role": r, "n": 0 if m is None else 2, "mean": m,
                       "min": m, "max": m}
                      for r, m in zip(("flywheel_harness", "claude_code"), means)]}


def record(roles=None, checkers=None, **over):
    doc = {"schema": "flywheel.graded_metric_report/v1", "run_ids": ["run-1"],
           "source_commits": ["abc"], "task_set_ids": ["flywheel_agentic_gauntlet_v1"],
           "counts": {"attempts": 14, "launched": 14, "scored": 10, "roles": 2,
                      "graded_checkers": 1},
           "roles": roles if roles is not None else [role("flywheel_harness"), role("claude_code")],
           "checkers": checkers if checkers is not None else [
               {"checker_id": "evidence_bound_reporting/v1", "task_ids": ["agt-015"],
                "scored_attempts": 4, "metrics": [metric("evidence_bound_score")]}],
           "does_not_prove": ["A mean over one repetition is a reading, not an estimate."]}
    doc.update(over)
    return doc


def test_no_record_states_the_measurement_was_not_taken():
    """Omitting the question would let the page show only its wins."""
    for text in (render_html(None), "\n".join(render_markdown(None))):
        assert NOT_RUN in text
    assert "## Head to head" in render_markdown(None)[0]


def test_an_empty_record_is_treated_the_same_as_no_record():
    """A run that produced no rows is not a run with a score of zero."""
    assert NOT_RUN in render_html(record(roles=[]))


def test_a_cost_the_provider_never_stated_is_never_drawn_as_a_total():
    """The dangerous case. A partial sum still looks whole on a page."""
    partial = role("claude_code", cost_usd_total=0.14, cost_reported_attempts=3,
                   cost_coverage=0.4286, cost_usd_per_scored_attempt=None,
                   null_reasons={"cost_usd_per_scored_attempt": "partial_cost_coverage"})
    cells = dict((label, text) for label, text, _ in role_cells(partial))
    assert cells["cost"] == "$0.1400" and cells["cost coverage"] == "43%"
    html = render_html(record(roles=[partial]))
    assert "only some attempts reported a cost" in html


def test_a_role_whose_provider_reports_no_cost_shows_the_absence_not_a_zero():
    free = role("codex_harness", cost_usd_total=None, cost_reported_attempts=0,
                cost_coverage=0.0, cost_usd_per_scored_attempt=None,
                null_reasons={"cost_usd_total": "provider_cost_unavailable",
                              "cost_usd_per_scored_attempt": "provider_cost_unavailable"})
    cells = dict((label, text) for label, text, _ in role_cells(free))
    assert cells["cost"] == ABSENT
    assert "$0" not in cells["cost"]
    assert "this provider states no cost" in render_html(record(roles=[free]))


def test_a_role_that_returned_nothing_gets_a_labelled_track_not_a_zero_bar():
    """A zero-width bar and an unmeasured one look identical at a glance."""
    blocked = role("cursor", attempts=7, launched=0, blocked=7, returned=0, scored=0,
                   launch_rate=0.0, readable_rate=0.0, pass_rate=None,
                   latency_ms_median=None, latency_ms_p90=None, cost_usd_total=None,
                   cost_reported_attempts=0, cost_coverage=None,
                   cost_usd_per_scored_attempt=None, output_tokens_total=None,
                   null_reasons={"cost_usd_total": "provider_cost_unavailable"})
    html = render_html(record(roles=[blocked]))
    assert "0 of 7 readable" in html
    assert 'style="width:0%"' not in html
    assert "unmeasured" in html


def test_every_counted_column_carries_its_own_denominator():
    """Seven attempts at 29 percent and seventy at 29 percent differ."""
    cells = dict((label, text) for label, text, _ in role_cells(role("a")))
    assert cells["launched"] == "7/7" and cells["readable"] == "5/7"


def test_latency_reads_in_seconds_once_an_attempt_outlasts_a_second():
    slow = dict((label, text) for label, text, _ in role_cells(role("a")))
    fast = dict((label, text) for label, text, _
                in role_cells(role("a", latency_ms_median=420.0)))
    assert slow["median latency"] == "4.2 s" and fast["median latency"] == "420 ms"


def test_a_checker_that_reported_no_numbers_says_so_instead_of_drawing_a_table():
    """Exactly what the first graded run produced. An empty table reads as zero."""
    empty = {"checker_id": "contradiction_detection/v1", "task_ids": ["agt-016"],
             "scored_attempts": 3, "metrics": []}
    html = render_html(record(checkers=[empty]))
    assert "reported no numeric evidence" in html
    assert "<table" in html  # the efficiency table still renders
    text = "\n".join(render_markdown(record(checkers=[empty])))
    assert "reported no numeric evidence" in text


def test_a_metric_one_harness_never_reported_is_absent_and_not_zero():
    partial = metric("fabricated_measurements", direction="lower", means=(0.0, None))
    checker = {"checker_id": "c/v1", "task_ids": ["t"], "scored_attempts": 2,
               "metrics": [partial]}
    html = render_html(record(checkers=[checker]))
    assert ABSENT in html
    row = [line for line in render_markdown(record(checkers=[checker]))
           if line.startswith("| fabricated_measurements")][0]
    assert row.endswith(f"| {ABSENT} |") and "| 0.0 |" in row


def test_a_run_with_no_graded_checker_says_the_quality_half_is_unmeasured():
    html = render_html(record(checkers=[]))
    assert "quality half of the comparison is unmeasured" in html


def test_every_metric_states_which_direction_is_better():
    """A bar with no orientation is decoration."""
    html = render_html(record(checkers=[
        {"checker_id": "c/v1", "task_ids": ["t"], "scored_attempts": 2,
         "metrics": [metric("false_pair_count", direction="lower")]}]))
    assert "lower is better" in html


def test_what_the_run_cannot_support_reaches_both_renderings():
    claim = "A mean over one repetition is a reading, not an estimate."
    assert claim in render_html(record())
    assert f"- {claim}" in render_markdown(record())


def test_a_hostile_role_name_cannot_inject_markup():
    html = render_html(record(roles=[role("<script>alert(1)</script>")]))
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_the_markdown_tables_are_rectangular():
    lines = render_markdown(record())
    tables = [line for line in lines if line.startswith("|")]
    assert tables, "no table rendered"
    widths = {line.count("|") for line in tables[:len(record()["roles"]) + 2]}
    assert len(widths) == 1, f"ragged table: {widths}"


def test_a_bar_cannot_contradict_the_caption_printed_inside_it():
    """The width and the label must come from the same two integers.

    A record whose stored rate disagrees with its own counts is not a state the
    rollup produces, which is exactly why nothing would catch it if the bar
    trusted the stored rate and the caption did not.
    """
    lying = role("a", scored=3, attempts=7, readable_rate=0.99)
    html = render_html(record(roles=[lying]))
    assert 'style="width:43%"' in html and "3/7" in html
    assert "99%" not in html


def test_a_low_readable_rate_carries_the_reason_it_is_low():
    """Otherwise the rate reads as a verdict on the harness, not its formatting."""
    mangled = role("codex_harness", scored=5, readable_rate=0.7143,
                   unreadable_reasons={"refused at the envelope": 1,
                                       "over the time budget": 1})
    html = render_html(record(roles=[mangled]))
    assert "1 refused at the envelope" in html
    assert "1 over the time budget" in html
    text = "\n".join(render_markdown(record(roles=[mangled])))
    assert "**codex_harness.** Ungraded: 1 refused at the envelope" in text


def test_a_role_with_nothing_to_explain_gets_no_note():
    clean = role("a", unreadable_reasons={})
    assert "ungraded" not in render_html(record(roles=[clean]))


def test_a_refusal_that_held_an_answer_reads_differently_from_one_that_did_not():
    """Otherwise a formatting gap and a capability gap draw the same bar."""
    chatty = role("claude_code", scored=2, readable_rate=0.2857,
                  unreadable_reasons={"refused at the envelope": 5},
                  envelope_recovery={"refused": 5, "held_an_envelope": 3, "unread": 0})
    html = render_html(record(roles=[chatty]))
    assert "3 of 5 refused answers held a complete envelope behind other text" in html
    assert "5 refused at the envelope" in html


def test_a_role_whose_outputs_were_never_read_makes_no_recovery_claim():
    """None means the probe did not run, which is not a finding of zero."""
    unprobed = role("a", unreadable_reasons={}, envelope_recovery=None)
    assert "refused answers held" not in render_html(record(roles=[unprobed]))


def test_a_recovered_refusal_is_drawn_beside_the_graded_bar_not_inside_it():
    """A checker never read it, so it must not extend the verdict-coloured fill."""
    chatty = role("claude_code", scored=2, attempts=7,
                  envelope_recovery={"refused": 5, "held_an_envelope": 3, "unread": 0})
    html = render_html(record(roles=[chatty]))
    assert 'class="fill" style="width:29%"' in html
    assert 'class="held" style="left:29%;width:43%"' in html
    assert HATCH_KEY in html


def test_a_harness_that_scored_nothing_still_says_so_over_its_hatch():
    """The row where the distinction matters most is also the easiest to lose.

    Zero readable draws no fill, so the hatch would be the only mark on the
    track and the count would go missing exactly where a reader needs it.
    """
    silent = role("local_14b", scored=0, attempts=7, pass_rate=None,
                  envelope_recovery={"refused": 7, "held_an_envelope": 3, "unread": 1})
    html = render_html(record(roles=[silent]))
    assert "0 of 7 readable" in html
    assert 'class="held" style="left:0%;width:43%"' in html
    assert 'style="width:0%"' not in html


def test_a_run_where_no_refusal_held_an_answer_prints_no_key_for_the_hatch():
    """A key to a mark that is not on the chart is a claim about a mark."""
    assert HATCH_KEY not in render_html(record(roles=[role("a")]))
