"""An instrument record checked against the driver reference it ran under.

This kind used to be an assumption wearing a schema. The example said in words
that the driver caps dispense flow at 200 uL/s and that nothing here re-checks
it, which is honest and is also why a device claim could never fail. A reference
file is what turns that sentence into a check.

  1. FIVE REFUTATIONS ARE AVAILABLE WITHOUT HARDWARE. An unknown command, an
     unlisted parameter, a parameter over the limit, a reading outside range,
     and a run outside its calibration window.
  2. NO REFERENCE IS UNVERIFIABLE, NEVER A PASS. An unchecked device claim
     reported as verified is the failure this kind exists to prevent.
  3. A REFERENCE FROM ANOTHER DRIVER DOES NOT BIND. A limit table from a
     different release is not the one the run was subject to.
  4. WHAT PASSES IS NARROW. The record is consistent with the driver's own
     reference. That the device did this, and that the reading is accurate, are
     not established here and the caveat says so.
"""
import json

import pytest

from harness.workstream import (
    REFUTED, UNVERIFIABLE, VERIFIED, Obligation, Workstream, WorkstreamError,
)
from harness.workstream_instrument import (
    instrument_checker, load_reference, load_references,
)
from harness.workstream_run import run_workstream

ENV = "mhs:liquid-handler-2/driver-1.4.0"

REFERENCE = {
    "schema": "flywheel.mhs.reference/v1",
    "device": "liquid-handler-2",
    "driver": "1.4.0",
    "calibration_valid_days": 30,
    "commands": {
        "dispense": {
            "parameters": {"flow_rate_ul_s": {"min": 1, "max": 200},
                           "volume_ul": {"min": 1, "max": 1000}},
            "readings": {"volume_ul": {"min": 0, "max": 1000}},
        },
    },
}

RECORD = {
    "device": "liquid-handler-2",
    "command": "dispense",
    "parameters": {"flow_rate_ul_s": 140, "volume_ul": 250},
    "readings": {"volume_ul": 249.4},
    "calibrated_at": "2026-08-20T09:00:00Z",
    "observed_at": "2026-09-01T14:30:00Z",
}

KNOWN = {"liquid-handler-2": REFERENCE}


def _ob(record=None, env=ENV, node="dispense"):
    body = dict(RECORD)
    body.update(record or {})
    return Obligation(
        obligation_id=node,
        statement=json.dumps(body),
        check="instrument",
        environment=env,
        depends_on=(),
    )


def _check(record=None, env=ENV, references=KNOWN):
    return instrument_checker(references)(_ob(record, env))


def test_a_record_inside_the_reference_passes_and_says_what_it_covered():
    verdict, detail = _check()
    assert verdict == "PASS"
    assert "dispense on liquid-handler-2 driver 1.4.0" in detail
    assert "2 parameter(s)" in detail
    assert "1 reading(s)" in detail


@pytest.mark.parametrize("record, fragment", [
    ({"command": "centrifuge"}, "lists no command named centrifuge"),
    ({"parameters": {"flow_rate_ul_s": 140, "pressure_kpa": 12}},
     "lists no parameter named pressure_kpa"),
    ({"parameters": {"flow_rate_ul_s": 260, "volume_ul": 250}},
     "flow_rate_ul_s is 260.0 and the reference limit is 200"),
    ({"parameters": {"flow_rate_ul_s": 0.5, "volume_ul": 250}},
     "flow_rate_ul_s is 0.5 and the reference floor is 1"),
    ({"readings": {"volume_ul": 1400}},
     "volume_ul is 1400.0 and the reference limit is 1000"),
    ({"calibrated_at": "2026-09-03T09:00:00Z"},
     "dated before the calibration it claims to run under"),
    ({"calibrated_at": "2026-06-01T09:00:00Z"},
     "and the reference allows 30"),
])
def test_the_five_refutations_a_reference_file_can_make_without_the_device(
        record, fragment):
    verdict, detail = _check(record)
    assert verdict == "FAIL"
    assert fragment in detail


def test_a_refutation_is_a_refutation_and_reaches_the_receipt():
    stream = Workstream([_ob({"parameters": {"flow_rate_ul_s": 260,
                                             "volume_ul": 250}})],
                        goal="dispense")
    receipt = run_workstream(stream, {"instrument": instrument_checker(KNOWN)})
    assert receipt["goal_standing"] == REFUTED


@pytest.mark.parametrize("env, references, fragment", [
    (ENV, {}, "no driver reference for liquid-handler-2 was supplied"),
    (ENV, {"plate-reader-3": REFERENCE}, "no driver reference for liquid-handler-2"),
    ("mhs:liquid-handler-2/driver-1.5.0", KNOWN, "the reference describes 1.4.0"),
    ("flywheel.units/v1", KNOWN, "does not name a device and driver"),
    ("mhs:liquid-handler-2", KNOWN, "does not name a device and driver"),
])
def test_a_reference_that_does_not_bind_settles_unverifiable_not_passing(
        env, references, fragment):
    # Never a pass. A device claim nothing checked, reported as verified, is
    # exactly the record this kind was written to make impossible.
    verdict, detail = _check(env=env, references=references)
    assert verdict == "UNVERIFIABLE"
    assert fragment in detail


def test_a_record_naming_another_device_than_the_environment_does_not_bind():
    verdict, detail = _check({"device": "plate-reader-3"})
    assert verdict == "UNVERIFIABLE"
    assert "the record names plate-reader-3" in detail
    assert "pins liquid-handler-2" in detail


@pytest.mark.parametrize("record, fragment", [
    ({"device": None}, "names its device"),
    ({"command": "   "}, "names its command"),
    ({"parameters": "flow_rate_ul_s=140"}, "object of name to number"),
    ({"parameters": {"flow_rate_ul_s": "140"}}, "must be a number"),
    ({"parameters": {"flow_rate_ul_s": True}}, "must be a number"),
    ({"observed_at": "yesterday"}, "observed_at must be an ISO-8601"),
    ({"calibrated_at": None}, "calibrated_at must be an ISO-8601"),
])
def test_a_statement_that_is_not_a_readable_instrument_record_is_refused(
        record, fragment):
    verdict, detail = _check(record)
    assert verdict == "FAIL"
    assert "not a readable instrument record" in detail
    assert fragment in detail


def test_a_naive_timestamp_is_read_as_utc_and_that_is_a_choice():
    inside, _ = _check({"calibrated_at": "2026-08-20T09:00:00",
                        "observed_at": "2026-09-01T14:30:00"})
    assert inside == "PASS"
    outside, detail = _check({"calibrated_at": "2026-06-01T09:00:00",
                              "observed_at": "2026-09-01T14:30:00"})
    assert outside == "FAIL"
    assert "the reference allows 30" in detail


def test_the_calibration_window_is_checked_at_its_edges():
    just_inside, _ = _check({"calibrated_at": "2026-08-02T14:30:00Z",
                             "observed_at": "2026-09-01T14:30:00Z"})
    assert just_inside == "PASS"
    just_outside, _ = _check({"calibrated_at": "2026-08-02T14:29:00Z",
                              "observed_at": "2026-09-01T14:30:00Z"})
    assert just_outside == "FAIL"


def test_a_reference_with_no_window_does_not_read_the_calibration_fields():
    open_ended = dict(REFERENCE)
    open_ended.pop("calibration_valid_days")
    verdict, _ = _check({"calibrated_at": "2019-01-01T00:00:00Z"},
                        references={"liquid-handler-2": open_ended})
    assert verdict == "PASS"


def _written(tmp_path, name, body):
    path = tmp_path / name
    path.write_text(json.dumps(body), encoding="utf-8")
    return path


def test_a_reference_file_is_read_and_its_shape_insisted_on_before_use(tmp_path):
    good = _written(tmp_path, "good.json", REFERENCE)
    assert load_reference(good)["device"] == "liquid-handler-2"
    with pytest.raises(WorkstreamError, match="no driver reference at"):
        load_reference(tmp_path / "absent.json")
    for name, body, fragment in [
        ("wrong-schema.json", {**REFERENCE, "schema": "something/v1"},
         "is not a flywheel.mhs.reference/v1 document"),
        ("no-device.json", {**REFERENCE, "device": "  "}, "names its device"),
        ("no-driver.json", {**REFERENCE, "driver": 1.4}, "names its driver"),
        ("no-commands.json", {**REFERENCE, "commands": {}},
         "lists at least one command"),
    ]:
        with pytest.raises(WorkstreamError, match=fragment):
            load_reference(_written(tmp_path, name, body))


def test_two_references_for_one_device_are_refused_rather_than_one_winning(tmp_path):
    first = _written(tmp_path, "first.json", REFERENCE)
    second = _written(tmp_path, "second.json",
                      {**REFERENCE, "driver": "1.5.0"})
    assert load_references([]) == {}
    assert sorted(load_references([first])) == ["liquid-handler-2"]
    with pytest.raises(WorkstreamError, match="two references describe"):
        load_references([first, second])


def test_a_passing_record_still_carries_what_a_reference_file_cannot_show():
    stream = Workstream([_ob()], goal="dispense")
    receipt = run_workstream(stream, {"instrument": instrument_checker(KNOWN)})
    assert receipt["goal_standing"] == VERIFIED
    caveat = " ".join(receipt["does_not_prove"])
    assert "consistent with what the driver permits" in caveat
    assert "not that the device performed the run" in caveat


def test_a_method_that_settled_nothing_does_not_get_a_caveat_saying_it_did():
    # The caveat is counted over what actually settled by the method. Printing
    # "checked against a driver reference file" over a run where no reference
    # was supplied would describe a check that never ran.
    stream = Workstream([_ob()], goal="dispense")
    receipt = run_workstream(stream, {"instrument": instrument_checker({})})
    caveat = " ".join(receipt["does_not_prove"])
    assert "driver reference file" not in caveat
    assert "1 obligation(s) under the goal are unverifiable" in caveat


def test_an_unbound_instrument_obligation_blocks_what_rests_on_it():
    stream = Workstream(
        [
            _ob(),
            Obligation("dose", '{"value": 0.25, "interval": [0.2, 0.3]}',
                       "arithmetic", "flywheel.units/v1", ("dispense",)),
        ],
        goal="dose",
    )
    receipt = run_workstream(stream, {"instrument": instrument_checker({})})
    assert receipt["obligations"]["dispense"]["standing"] == UNVERIFIABLE
    assert receipt["goal_standing"] != VERIFIED
    assert receipt["run"]["skipped"] == 1
