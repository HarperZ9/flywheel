import json

import pytest

from harness.inspect_evidence import InspectImportError, import_inspect_log


def _raw(value):
    return json.dumps(value, separators=(",", ":")).encode("utf-8")


def _valid_log(**overrides):
    doc = {
        "version": 2,
        "status": "success",
        "eval": {"task": "task", "model": "model", "run_id": "run"},
        "results": {"total_samples": 1, "completed_samples": 1},
        "samples": [
            {"id": "s1", "epoch": 1, "scores": {"match": {"value": "C"}}},
        ],
    }
    doc.update(overrides)
    return doc


def _epoch_log():
    samples = []
    for sample_id in ("a", "b"):
        for epoch in (1, 2):
            samples.append({
                "id": sample_id,
                "epoch": epoch,
                "scores": {"match": {"value": "C"}},
            })
    return _valid_log(
        results={"total_samples": 4, "completed_samples": 4, "scores": [
            {"name": "match", "scorer": "match", "scored_samples": 2, "unscored_samples": 0},
        ]},
        samples=samples,
    )


def _pointers(doc):
    return {item["json_pointer"]: item["source_value"] for item in doc["source_pointers"]}


def test_missing_invalidated_defaults_to_false_without_source_pointer():
    doc = import_inspect_log(_raw(_valid_log()))

    assert doc["invalidated"] is False
    assert doc["assessment"] == "reported"
    assert doc["scoring_coverage"]["coverage_complete"] is True
    assert "/invalidated" not in _pointers(doc)


def test_explicit_false_invalidated_is_retained_with_source_pointer():
    doc = import_inspect_log(_raw(_valid_log(invalidated=False)))

    assert doc["invalidated"] is False
    assert doc["assessment"] == "reported"
    assert _pointers(doc)["/invalidated"] is False


def test_config_limit_is_preserved_when_it_is_a_range_not_a_denominator():
    doc = import_inspect_log(_raw(_valid_log(eval={
        "task": "task",
        "model": "model",
        "run_id": "run",
        "config": {"limit": [1, 3]},
    })))

    assert doc["counts"]["config_limit"] == [1, 3]
    assert doc["counts"]["config_limit_pointer"] == "/eval/config/limit"
    assert "expected_samples" not in doc["counts"]


def test_true_invalidated_log_is_incomplete_even_when_counts_and_scores_match():
    doc = import_inspect_log(_raw(_valid_log(invalidated=True)))

    assert doc["invalidated"] is True
    assert doc["assessment"] == "incomplete"
    assert doc["scoring_coverage"]["coverage_complete"] is False
    assert _pointers(doc)["/invalidated"] is True
    assert any("invalidated" in reason for reason in doc["does_not_prove"])


@pytest.mark.parametrize("flag", [0, 1, None, "false", [], {}])
def test_malformed_invalidated_flag_is_rejected(flag):
    with pytest.raises(InspectImportError):
        import_inspect_log(_raw(_valid_log(invalidated=flag)))


def test_stale_zero_aggregate_score_counts_are_rejected():
    doc = _valid_log(results={"total_samples": 1, "completed_samples": 1, "scores": [
        {"name": "match", "scorer": "match", "scored_samples": 0, "unscored_samples": 0},
    ]})

    with pytest.raises(InspectImportError):
        import_inspect_log(_raw(doc))


def test_missing_result_scorer_on_observed_sample_marks_coverage_incomplete():
    doc = _valid_log(
        results={"total_samples": 2, "completed_samples": 2, "scores": [
            {"name": "match", "scorer": "match", "scored_samples": 1, "unscored_samples": 0},
        ]},
        samples=[
            {"id": "s1", "epoch": 1, "scores": {"match": {"value": "C"}}},
            {"id": "s2", "epoch": 1, "scores": {"other": {"value": "C"}}},
        ],
    )

    imported = import_inspect_log(_raw(doc))

    assert imported["assessment"] == "incomplete"
    assert imported["scoring_coverage"]["coverage_complete"] is False


def test_epoch_reducer_aggregate_count_can_match_distinct_sample_ids():
    imported = import_inspect_log(_raw(_epoch_log()))

    assert imported["assessment"] == "reported"
    assert imported["counts"]["observed_samples"] == 4
    assert imported["scoring_coverage"]["coverage_complete"] is True


@pytest.mark.parametrize("value", [None, [None], ["C", None]])
def test_null_scalar_or_sequence_score_is_not_a_completed_inspect_score(value):
    doc = _valid_log()
    doc["samples"][0]["scores"]["match"]["value"] = value
    with pytest.raises(InspectImportError):
        import_inspect_log(_raw(doc))


def test_inspect_mapping_score_can_preserve_null_component_without_quality_claim():
    doc = _valid_log()
    doc["samples"][0]["scores"]["match"]["value"] = {"manual": None, "machine": "C"}
    imported = import_inspect_log(_raw(doc))
    assert imported["semantic_verification"] == "UNVERIFIABLE"
    assert imported["samples"][0]["scores"][0]["value"] == {"manual": None, "machine": "C"}
