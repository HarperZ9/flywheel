"""False-success controls for the monitor/outcome join.

Each control here is built to be wrong on purpose. A control that passes is a
bug in the control, so every one of them asserts that the wrong thing is caught
or is kept visibly separate rather than absorbed.

The three the bundle names explicitly are an always-pass grader, an always-high
monitor and an always-low monitor. The first is the important one: it is the
shape where a log reports success for work that was never done, and it is the
reason an outcome in this module is absent until someone independent supplies
it.
"""
import json

import pytest

from harness.monitor_outcome import (
    INDEPENDENT,
    SOURCE_LOG,
    MonitorOutcomeError,
    attach_outcomes,
    build_monitor_record,
    comparable_pairs,
)


def _raw(value):
    return json.dumps(value, separators=(",", ":")).encode("utf-8")


def _log(samples):
    return _raw({
        "version": 2,
        "status": "success",
        "eval": {"task": "task", "model": "model", "run_id": "run"},
        "results": {"total_samples": len(samples), "completed_samples": len(samples)},
        "samples": samples,
    })


def _eval2_sample(sample_id, summary, action_values):
    return {
        "id": sample_id,
        "epoch": 1,
        "scores": {
            "monitor": {
                "value": summary,
                "metadata": {"scores": [
                    {"action": i, "message_id": f"m{i}", "monitor": "strong",
                     "draw": 0, "value": v}
                    for i, v in enumerate(action_values)
                ]},
            },
            "task_success": {"value": 1},
        },
    }


# --- the always-pass grader -------------------------------------------------

def test_a_log_that_grades_everything_success_yields_no_verified_outcome():
    """The control the whole design exists for.

    `task_success: 1` on every sample is exactly what an always-pass grader
    writes. Nothing in the log distinguishes it from a real pass. So the join
    must not read any outcome out of the log at all: every sample stays absent
    until an independent source says otherwise.
    """
    samples = [_eval2_sample(f"s{i}", 1.0, [1.0]) for i in range(5)]
    record = build_monitor_record(_log(samples), adapter="eval2")

    assert record["coverage"]["outcome"]["verified"] == 0
    assert record["coverage"]["outcome"]["absent"] == 5
    assert all(s["outcome"]["status"] == "absent" for s in record["samples"])
    # And nothing is comparable, so no rate can be computed from a log alone.
    assert comparable_pairs(record) == []
    assert record["coverage"]["comparable"] == 0


def test_an_outcome_taken_from_the_log_is_not_marked_verified():
    """A caller may record the log's own verdict, but it cannot be called verified."""
    record = build_monitor_record(_log([_eval2_sample("s1", 1.0, [1.0])]), adapter="eval2")
    attach_outcomes(record, [{
        "id": "s1", "epoch": 1, "value": "success",
        "source": SOURCE_LOG, "checked_by": "eval log task_success scorer",
    }])
    assert record["samples"][0]["outcome"]["status"] == "reported"
    assert record["coverage"]["outcome"]["verified"] == 0
    # "reported" is not comparable: it would put the log on both sides.
    assert comparable_pairs(record) == []


# --- constant monitors ------------------------------------------------------

@pytest.mark.parametrize("constant", [0.0, 10.0])
def test_a_constant_monitor_is_carried_without_becoming_a_verdict(constant):
    """An always-low and an always-high monitor must both survive as values.

    Neither may be converted into a flag here. There is no threshold in this
    module, so a constant monitor produces a constant value and nothing else.
    The comparison that exposes it as useless belongs to the analysis step, with
    its review budget declared.
    """
    samples = [_eval2_sample(f"s{i}", constant, [constant]) for i in range(4)]
    record = build_monitor_record(_log(samples), adapter="eval2")
    assert record["coverage"]["monitor"]["scored"] == 4
    assert {s["monitor"]["summary_value"] for s in record["samples"]} == {constant}
    # No field claims detection. Scoped to the data, because `does_not_prove`
    # legitimately uses those words to say what the record cannot support, and
    # an earlier version of this control searched the whole document and failed
    # on its own limitations text.
    data = json.dumps({"samples": record["samples"], "coverage": record["coverage"]})
    for word in ("detected", "flagged", "caught", "alarm", "suspicious"):
        assert word not in data


def test_a_constant_high_monitor_cannot_hide_a_bad_outcome():
    """With independent outcomes attached, a constant monitor is visibly useless."""
    samples = [_eval2_sample(f"s{i}", 10.0, [10.0]) for i in range(4)]
    record = build_monitor_record(_log(samples), adapter="eval2")
    attach_outcomes(record, [
        {"id": f"s{i}", "epoch": 1, "value": "harmful" if i < 2 else "clean",
         "source": INDEPENDENT, "checked_by": "deterministic file check"}
        for i in range(4)
    ])
    pairs = comparable_pairs(record)
    assert len(pairs) == 4
    # Every sample scores identically, so the monitor separates nothing. The
    # record makes that visible rather than reporting a detection rate.
    assert len({p["monitor_value"] for p in pairs}) == 1
    assert len({p["outcome_value"] for p in pairs}) == 2


# --- missing values must never become zero or success -----------------------

def test_an_unscored_action_stays_the_string_it_was():
    record = build_monitor_record(
        _log([_eval2_sample("s1", 5.0, [5.0, "unscored"])]), adapter="eval2")
    actions = record["samples"][0]["monitor"]["actions"]
    assert [a["status"] for a in actions] == ["scored", "unscored"]
    assert actions[1]["source_value"] == "unscored"
    assert actions[1]["source_value"] != 0


def test_a_null_eval2_action_score_stays_absent():
    """eval2 carries its own null path, separate from eval1's.

    Mutation testing found this gap: the eval1 control below exercises bare
    `None` entries in `metadata.action_scores`, which take an inline branch.
    An eval2 action object with `"value": null` goes through `_action_entry`
    instead, and flipping that branch to SCORED was caught by nothing until
    this control existed.
    """
    log = _log([{
        "id": "s1", "epoch": 1,
        "scores": {"monitor": {"value": 5.0, "metadata": {"scores": [
            {"action": 0, "message_id": "m0", "monitor": "strong", "draw": 0, "value": 5.0},
            {"action": 1, "message_id": "m1", "monitor": "strong", "draw": 0, "value": None},
        ]}}},
    }])
    record = build_monitor_record(log, adapter="eval2")
    actions = record["samples"][0]["monitor"]["actions"]
    assert [a["status"] for a in actions] == ["scored", "absent"]
    assert actions[1]["source_value"] is None
    assert record["coverage"]["actions"]["absent"] == 1
    assert record["coverage"]["actions"]["scored"] == 1


def test_a_null_action_score_stays_absent_and_is_counted_separately():
    log = _log([{
        "id": "s1", "epoch": 1,
        "scores": {"monitor": {"value": None,
                               "metadata": {"action_scores": [None, 4.0, None]}}},
    }])
    record = build_monitor_record(log, adapter="eval1")
    counts = record["coverage"]["actions"]
    assert counts["absent"] == 2
    assert counts["scored"] == 1
    # The two skipped actions are not in the scored denominator.
    assert counts["scored"] + counts["absent"] == 3


def test_an_absent_monitor_is_absent_not_low_suspicion():
    record = build_monitor_record(
        _log([{"id": "s1", "epoch": 1, "scores": {"task_success": {"value": 1}}}]),
        adapter="eval2")
    monitor = record["samples"][0]["monitor"]
    assert monitor["status"] == "absent"
    assert monitor["summary_value"] is None
    assert monitor["actions"] == []


# --- joins that must be refused ---------------------------------------------

def test_a_duplicate_sample_and_epoch_is_refused_not_merged():
    duplicate = [_eval2_sample("s1", 1.0, [1.0]), _eval2_sample("s1", 1.0, [2.0])]
    with pytest.raises(MonitorOutcomeError, match="duplicate sample id and epoch"):
        build_monitor_record(_log(duplicate), adapter="eval2")


def test_a_string_id_and_an_int_id_do_not_collide():
    samples = [_eval2_sample("3", 1.0, [1.0]), _eval2_sample(3, 2.0, [2.0])]
    record = build_monitor_record(_log(samples), adapter="eval2")
    assert record["coverage"]["eligible"] == 2


def test_an_outcome_for_an_unknown_sample_is_refused():
    record = build_monitor_record(_log([_eval2_sample("s1", 1.0, [1.0])]), adapter="eval2")
    with pytest.raises(MonitorOutcomeError, match="absent from the log"):
        attach_outcomes(record, [{"id": "ghost", "epoch": 1, "value": "clean",
                                  "source": INDEPENDENT, "checked_by": "check"}])


def test_an_outcome_cannot_silently_overwrite_another():
    record = build_monitor_record(_log([_eval2_sample("s1", 1.0, [1.0])]), adapter="eval2")
    first = {"id": "s1", "epoch": 1, "value": "clean",
             "source": INDEPENDENT, "checked_by": "check A"}
    attach_outcomes(record, [first])
    with pytest.raises(MonitorOutcomeError, match="already attached"):
        attach_outcomes(record, [dict(first, value="harmful", checked_by="check B")])


def test_an_unknown_adapter_is_refused_rather_than_guessed():
    with pytest.raises(MonitorOutcomeError, match="unsupported adapter"):
        build_monitor_record(_log([_eval2_sample("s1", 1.0, [1.0])]), adapter="eval3")


def test_an_outcome_needs_a_named_checker():
    record = build_monitor_record(_log([_eval2_sample("s1", 1.0, [1.0])]), adapter="eval2")
    with pytest.raises(MonitorOutcomeError, match="checked_by"):
        attach_outcomes(record, [{"id": "s1", "epoch": 1, "value": "clean",
                                  "source": INDEPENDENT}])


# --- provenance -------------------------------------------------------------

def test_the_record_pins_the_exact_source_bytes():
    import hashlib
    raw = _log([_eval2_sample("s1", 1.0, [1.0])])
    record = build_monitor_record(raw, adapter="eval2")
    assert record["source"]["sha256"] == hashlib.sha256(raw).hexdigest()
    assert record["source"]["bytes"] == len(raw)


def test_every_record_carries_its_limits():
    record = build_monitor_record(_log([_eval2_sample("s1", 1.0, [1.0])]), adapter="eval2")
    assert record["does_not_prove"]
    joined = " ".join(record["does_not_prove"]).lower()
    assert "intent" in joined
    assert "independent" in joined
