"""Malformed evidence must not acquire scored or independently checked status."""
import copy
import json

import pytest
from monitor_outcome_shapes import eval2_sample, log

from harness.monitor_outcome import (
    INDEPENDENT,
    MonitorOutcomeError,
    attach_outcomes,
    build_monitor_record,
    exclude_samples,
)


def record():
    return build_monitor_record(log([eval2_sample("s1", [1.0])], eval2=True), adapter="eval2")


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity", "1e400"])
def test_nonfinite_source_numbers_are_rejected(token):
    raw = log([eval2_sample("s1", [1.0])], eval2=True).replace(b"1.0", token.encode())
    with pytest.raises(MonitorOutcomeError, match="non-finite"):
        build_monitor_record(raw, adapter="eval2")


def test_duplicate_source_keys_are_rejected():
    raw = log([eval2_sample("s1", [1.0])], eval2=True)
    raw = raw.replace(b'"samples":', b'"samples": [], "samples":', 1)
    with pytest.raises(MonitorOutcomeError, match="duplicate JSON key"):
        build_monitor_record(raw, adapter="eval2")


@pytest.mark.parametrize("field,bad", [
    ("id", None), ("id", True), ("id", 1.5), ("id", []),
    ("epoch", None), ("epoch", True), ("epoch", "1"), ("epoch", 1.0),
])
def test_source_sample_keys_follow_the_importer_contract(field, bad):
    sample = eval2_sample("s1", [1.0])
    sample[field] = bad
    with pytest.raises(MonitorOutcomeError, match="sample id|epoch"):
        build_monitor_record(log([sample], eval2=True), adapter="eval2")


@pytest.mark.parametrize("checker", [None, "", "   ", False, 0, {}, []])
def test_an_empty_or_nontext_checker_cannot_create_a_verified_outcome(checker):
    original = record()
    before = copy.deepcopy(original)
    with pytest.raises(MonitorOutcomeError, match="checked_by"):
        attach_outcomes(original, [{"id": "s1", "epoch": 1, "value": "clean",
                                   "source": INDEPENDENT, "checked_by": checker}])
    assert original == before


def test_boolean_epoch_cannot_join_an_integer_epoch():
    original = record()
    with pytest.raises(MonitorOutcomeError, match="epoch"):
        attach_outcomes(original, [{"id": "s1", "epoch": True, "value": "clean",
                                   "source": INDEPENDENT, "checked_by": "test checker"}])
    assert original["coverage"]["comparable"] == 0


def test_valid_independent_outcome_keeps_its_checker_and_provenance():
    original = record()
    attach_outcomes(original, [{"id": "s1", "epoch": 1, "value": False,
                               "source": INDEPENDENT, "checked_by": "test checker"}])
    assert original["coverage"]["comparable"] == 1
    assert original["samples"][0]["outcome"] == {
        "status": "verified", "value": False,
        "source": INDEPENDENT, "checked_by": "test checker",
    }
    json.dumps(original, allow_nan=False)


@pytest.mark.parametrize("value", [None, float("nan"), float("inf"),
                                  {"nested": [float("nan")]}, (), {1: "value"}])
def test_missing_or_non_json_outcomes_cannot_be_verified(value):
    original = record()
    before = copy.deepcopy(original)
    with pytest.raises(MonitorOutcomeError, match="value"):
        attach_outcomes(original, [{"id": "s1", "epoch": 1, "value": value,
                                   "source": INDEPENDENT, "checked_by": "checker"}])
    assert original == before


@pytest.mark.parametrize("field", ["reason", "evidence"])
@pytest.mark.parametrize("value", [0, False, "", "   ", None, []])
def test_exclusions_require_text_reason_and_evidence(field, value):
    original = record()
    before = copy.deepcopy(original)
    item = {"id": "s1", "epoch": 1, "reason": "precondition", "evidence": "receipt"}
    item[field] = value
    with pytest.raises(MonitorOutcomeError, match=field):
        exclude_samples(original, [item])
    assert original == before


@pytest.mark.parametrize("operation", [attach_outcomes, exclude_samples])
@pytest.mark.parametrize("second_id", ["missing", "s1"])
def test_failed_batches_leave_the_entire_record_unchanged(operation, second_id):
    original = record()
    before = copy.deepcopy(original)
    item = {"id": "s1", "epoch": 1, "value": False,
            "source": INDEPENDENT, "checked_by": "checker",
            "reason": "precondition", "evidence": "receipt"}
    with pytest.raises(MonitorOutcomeError):
        operation(original, [item, dict(item, id=second_id)])
    assert original == before


def test_mapping_only_negative_eval1_score_cannot_be_compared():
    sample = {"id": "s1", "epoch": 1,
              "scores": {"monitor_strong": {"value": {"0": -1}}}}
    original = build_monitor_record(log([sample], eval2=False), adapter="eval1")
    attach_outcomes(original, [{"id": "s1", "epoch": 1, "value": False,
                               "source": INDEPENDENT, "checked_by": "checker"}])
    assert original["samples"][0]["monitor"]["status"] == "unscored"
    assert original["coverage"]["comparable"] == 0


@pytest.mark.parametrize("member", ["action_0", "trajectory", "max"])
@pytest.mark.parametrize("value,status,comparable", [(-1, "unscored", 0), (0, "scored", 1)])
def test_legacy_negative_scores_are_unscored_but_zero_is_valid(member, value, status, comparable):
    sample = {"id": "s1", "epoch": 1,
              "scores": {"monitor_strong": {"value": {member: value}}}}
    original = build_monitor_record(log([sample], eval2=False), adapter="eval1-legacy")
    attach_outcomes(original, [{"id": "s1", "epoch": 1, "value": False,
                               "source": INDEPENDENT, "checked_by": "checker"}])
    assert original["samples"][0]["monitor"]["status"] == status
    assert original["coverage"]["comparable"] == comparable
