"""Falsifiers for the reason an attempt never reached a grader.

The published comparison reports a readable rate per harness. Without these
counts, a harness that answered correctly and mis-formatted its envelope and a
harness that never produced an answer are the same number on the page. So the
tests below are about keeping those two apart, and about not quietly inventing
a category for a failure nobody has seen before.
"""
from harness.attempt_attribution import (LABELS, UNATTRIBUTED, attribute, envelope_recoverable,
                                         label_for, recovery, recovery_sentence, summarize)


def row(*, launched=True, state="pass", failure=""):
    return {"launched": launched, "oracle_state": state, "failure_class": failure}


def test_a_graded_attempt_is_never_counted_as_a_failure():
    assert attribute([row(state="pass"), row(state="fail")]) == {}


def test_the_two_ways_an_answer_goes_ungraded_stay_apart():
    """A malformed envelope and a missing answer are different products."""
    counts = attribute([row(state="not_run", failure="_MalformedAttempt"),
                        row(state="not_run", failure="timeout")])
    assert counts == {LABELS["_MalformedAttempt"]: 1, LABELS["timeout"]: 1}


def test_an_unrecognised_class_keeps_its_own_name():
    """A bucket is where a new failure mode goes to stop being noticed."""
    counts = attribute([row(state="not_run", failure="provider_refused_request")])
    assert counts == {"provider_refused_request": 1}
    assert "other" not in counts


def test_a_failure_with_no_class_is_named_rather_than_dropped():
    assert attribute([row(state="not_run")]) == {UNATTRIBUTED: 1}
    assert label_for(None) == UNATTRIBUTED


def test_an_attempt_that_never_launched_is_not_an_answer_failure():
    """That is a gate fact, which the launch rate already carries."""
    assert attribute([row(launched=False, state="not_run", failure="endpoint_down")]) == {}


def test_the_common_reason_is_reported_first():
    rows = ([row(state="not_run", failure="timeout")]
            + [row(state="not_run", failure="_MalformedAttempt")] * 3)
    assert list(attribute(rows)) == [LABELS["_MalformedAttempt"], LABELS["timeout"]]


def test_the_internal_exception_name_never_reaches_a_reader():
    """`_MalformedAttempt` is a Python class, not an explanation."""
    counts = attribute([row(state="not_run", failure="_MalformedAttempt")])
    assert "_MalformedAttempt" not in counts
    assert "envelope" in next(iter(counts))


def test_a_run_with_nothing_to_explain_says_nothing():
    assert summarize({}) == ""


def test_the_sentence_carries_every_reason_with_its_count():
    text = summarize(attribute([row(state="not_run", failure="timeout"),
                                row(state="not_run", failure="timeout"),
                                row(state="not_run", failure="_MalformedAttempt")]))
    assert "2 " + LABELS["timeout"] in text
    assert "1 " + LABELS["_MalformedAttempt"] in text


def refused(path="out.txt"):
    return {"launched": True, "oracle_state": "not_run", "failure_class": "_MalformedAttempt",
            "raw_output_path": path, "rejected_output_path": ""}


def test_the_two_malformed_classes_are_not_the_same_failure():
    """One is refused at the envelope. The other reached a checker."""
    assert LABELS["_MalformedAttempt"] != LABELS["oracle_malformed"]
    assert "inside" in LABELS["oracle_malformed"]


def test_an_answer_behind_a_sentence_of_prose_is_found():
    """The common real case. Refusing it was right; calling it absent is wrong."""
    assert envelope_recoverable('I have everything I need.\n\n{"artifacts": {"a.md": "x"}}')


def test_an_answer_with_one_stray_brace_after_it_is_found():
    assert envelope_recoverable('{"artifacts": {"a.md": "x"}}}')


def test_reasoning_that_never_became_an_answer_is_not_recovered():
    """A quarter megabyte of streamed thought is the capability gap."""
    stream = "\n".join('{"type": "reasoning", "text": "thinking"}' for _ in range(500))
    assert not envelope_recoverable(stream)


def test_an_object_that_is_not_the_envelope_is_not_recovered():
    """`artifacts` alongside anything else is a different document."""
    assert not envelope_recoverable('{"artifacts": {"a.md": "x"}, "notes": "hi"}')
    assert not envelope_recoverable('{"artifacts": "not an object"}')


def test_a_role_with_no_envelope_refusals_reports_nothing_rather_than_zero():
    rows = [{"launched": True, "oracle_state": "pass"},
            {"launched": True, "oracle_state": "not_run", "failure_class": "timeout"}]
    assert recovery(rows, lambda path: "") is None


def test_an_artifact_refused_inside_an_accepted_envelope_is_not_probed():
    """A checker already graded it. Re-reading its output would double count."""
    rows = [{"launched": True, "oracle_state": "not_run", "failure_class": "oracle_malformed",
             "raw_output_path": "out.txt"}]
    assert recovery(rows, lambda path: '{"artifacts": {"a.md": "x"}}') is None


def test_an_output_that_cannot_be_read_is_unread_and_never_guessed():
    """A record can outlive its artifacts. Absent evidence is not evidence."""
    counts = recovery([refused(), refused()], lambda path: None)
    assert counts == {"refused": 2, "held_an_envelope": 0, "unread": 2}
    assert "2 with no output to read" in recovery_sentence(counts)


def test_the_rejected_output_is_read_when_the_raw_one_is_gone():
    """A refusal past the retention cap writes only the rejected stream."""
    row = refused(path="")
    row["rejected_output_path"] = "rejected.txt"
    reads = {"rejected.txt": '{"artifacts": {"a.md": "x"}}'}
    counts = recovery([row], lambda path: reads.get(path))
    assert counts == {"refused": 1, "held_an_envelope": 1, "unread": 0}


def test_the_sentence_says_how_many_of_how_many():
    counts = recovery([refused("a"), refused("b"), refused("c")],
                      lambda path: '{"artifacts": {}}' if path != "c" else "no answer here")
    assert counts["held_an_envelope"] == 2
    assert recovery_sentence(counts).startswith("2 of 3 refused answers held a complete envelope")
    assert recovery_sentence(None) == ""


def test_the_failure_classes_a_real_run_produced_read_as_english():
    """Named after the 2026-09-04 run, where all three reached the page raw.

    `BackendError` is the one that matters most. Four of local_32b's seven
    attempts were an unreachable Ollama endpoint, and a reader who sees the
    class name reads 1 of 7 readable as a verdict on a 32B model.
    """
    for name in ("malformed_jsonl", "malformed_provider_output", "BackendError"):
        assert name not in attribute([row(state="not_run", failure=name)])
    assert label_for("BackendError") == "the model endpoint did not answer"
    assert "endpoint" in label_for("BackendError")


def test_the_two_unreadable_streams_are_not_collapsed_into_one_reason():
    """One is the harness's own provider. The other is a provider it drives."""
    assert LABELS["malformed_jsonl"] != LABELS["malformed_provider_output"]
    assert "inner" in LABELS["malformed_provider_output"]
