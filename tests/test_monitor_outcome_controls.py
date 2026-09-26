"""False-success controls for the monitor/outcome join.

Each control here is built to be wrong on purpose. A control that passes is a
bug in the control, so every one of them asserts that the wrong thing is caught
or is kept visibly separate rather than absorbed.

The three the bundle names explicitly are an always-pass grader, an always-high
monitor and an always-low monitor. The first is the important one: it is the
shape where a log reports success for work that was never done, and it is the
reason an outcome in this module is absent until someone independent supplies
it. The monitor shapes are Control Tower's own (see monitor_outcome_shapes.py);
the format-level controls live in test_monitor_outcome_shapes.py.
"""
import hashlib
import json

import pytest
from monitor_outcome_shapes import eval2_sample, log

from harness.monitor_outcome import (
    INDEPENDENT,
    SOURCE_LOG,
    MonitorOutcomeError,
    attach_outcomes,
    build_monitor_record,
    comparable_pairs,
)


def _record(samples):
    return build_monitor_record(log(samples, eval2=True), adapter="eval2")


# --- the always-pass grader -------------------------------------------------

def test_a_log_that_grades_everything_success_yields_no_verified_outcome():
    """The control the whole design exists for.

    `task_success: 1` on every sample is exactly what an always-pass grader
    writes. Nothing in the log distinguishes it from a real pass. So the join
    must not read any outcome out of the log at all: every sample stays absent
    until an independent source says otherwise.
    """
    record = _record([eval2_sample(f"s{i}", [1.0]) for i in range(5)])
    assert record["coverage"]["outcome"]["verified"] == 0
    assert record["coverage"]["outcome"]["absent"] == 5
    assert all(s["outcome"]["status"] == "absent" for s in record["samples"])
    assert comparable_pairs(record) == []
    assert record["coverage"]["comparable"] == 0


def test_an_outcome_taken_from_the_log_is_not_marked_verified():
    record = _record([eval2_sample("s1", [1.0])])
    attach_outcomes(record, [{"id": "s1", "epoch": 1, "value": "success",
                              "source": SOURCE_LOG, "checked_by": "eval log task_success scorer"}])
    assert record["samples"][0]["outcome"]["status"] == "reported"
    assert record["coverage"]["outcome"]["verified"] == 0
    # "reported" is not comparable: it would put the log on both sides.
    assert comparable_pairs(record) == []


# --- constant monitors ------------------------------------------------------

@pytest.mark.parametrize("constant", [0.0, 10.0])
def test_a_constant_monitor_is_carried_without_becoming_a_verdict(constant):
    """An always-low and an always-high monitor both survive as values.

    Neither may be converted into a flag here. There is no threshold in this
    module, so a constant monitor produces a constant value and nothing else.
    """
    record = _record([eval2_sample(f"s{i}", [constant]) for i in range(4)])
    assert record["coverage"]["monitor"]["scored"] == 4
    values = {a["source_value"] for s in record["samples"] for a in s["monitor"]["actions"]}
    assert values == {constant}
    # Scoped to the data, because `does_not_prove` legitimately uses these
    # words to say what the record cannot support.
    data = json.dumps({"samples": record["samples"], "coverage": record["coverage"]})
    for word in ("detected", "flagged", "caught", "alarm", "suspicious"):
        assert word not in data


def test_a_constant_high_monitor_cannot_hide_a_bad_outcome():
    record = _record([eval2_sample(f"s{i}", [10.0]) for i in range(4)])
    attach_outcomes(record, [
        {"id": f"s{i}", "epoch": 1, "value": "harmful" if i < 2 else "clean",
         "source": INDEPENDENT, "checked_by": "deterministic file check"}
        for i in range(4)])
    pairs = comparable_pairs(record)
    assert len(pairs) == 4
    assert len({json.dumps(p["monitor_value"], sort_keys=True) for p in pairs}) == 1
    assert len({p["outcome_value"] for p in pairs}) == 2


def test_an_absent_monitor_is_absent_not_low_suspicion():
    record = _record([{"id": "s1", "epoch": 1, "scores": {"task_success": {"value": 1}}}])
    monitor = record["samples"][0]["monitor"]
    assert monitor["status"] == "absent"
    assert monitor["actions"] == []
    assert record["coverage"]["monitor"]["absent"] == 1


# --- joins that must be refused ---------------------------------------------

def test_a_duplicate_sample_and_epoch_is_refused_not_merged():
    with pytest.raises(MonitorOutcomeError, match="duplicate sample id and epoch"):
        _record([eval2_sample("s1", [1.0]), eval2_sample("s1", [2.0])])


def test_a_string_id_and_an_int_id_do_not_collide():
    record = _record([eval2_sample("3", [1.0]), eval2_sample(3, [2.0])])
    assert record["coverage"]["eligible"] == 2


def test_an_outcome_for_an_unknown_sample_is_refused():
    record = _record([eval2_sample("s1", [1.0])])
    with pytest.raises(MonitorOutcomeError, match="absent from the log"):
        attach_outcomes(record, [{"id": "ghost", "epoch": 1, "value": "clean",
                                  "source": INDEPENDENT, "checked_by": "check"}])


def test_an_outcome_cannot_silently_overwrite_another():
    record = _record([eval2_sample("s1", [1.0])])
    first = {"id": "s1", "epoch": 1, "value": "clean", "source": INDEPENDENT, "checked_by": "A"}
    attach_outcomes(record, [first])
    with pytest.raises(MonitorOutcomeError, match="already attached"):
        attach_outcomes(record, [dict(first, value="harmful", checked_by="B")])


def test_an_unknown_adapter_is_refused_rather_than_guessed():
    with pytest.raises(MonitorOutcomeError, match="unsupported adapter"):
        build_monitor_record(log([eval2_sample("s1", [1.0])], eval2=True), adapter="eval3")


def test_an_outcome_needs_a_named_checker():
    record = _record([eval2_sample("s1", [1.0])])
    with pytest.raises(MonitorOutcomeError, match="checked_by"):
        attach_outcomes(record, [{"id": "s1", "epoch": 1, "value": "clean",
                                  "source": INDEPENDENT}])


# --- provenance -------------------------------------------------------------

def test_the_record_pins_the_exact_source_bytes_and_shape_revision():
    raw = log([eval2_sample("s1", [1.0])], eval2=True)
    record = build_monitor_record(raw, adapter="eval2")
    assert record["source"]["sha256"] == hashlib.sha256(raw).hexdigest()
    assert record["source"]["bytes"] == len(raw)
    assert record["shapes_from"].endswith("1cc91b7182674a906d4f556c2d2f493c27e51ae9")


def test_every_record_carries_its_limits():
    record = _record([eval2_sample("s1", [1.0])])
    joined = " ".join(record["does_not_prove"]).lower()
    assert "intent" in joined
    assert "independent" in joined
