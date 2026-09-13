import hashlib
import json
import pytest

def _api():
    try:
        from harness.inspect_evidence import InspectImportError, import_inspect_log
    except ModuleNotFoundError as exc:
        pytest.fail(f"missing inspect evidence import API: {exc}")
    return import_inspect_log, InspectImportError

def _raw(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

def _by_pointer(doc):
    return {item["json_pointer"]: item["source_value"] for item in doc["source_pointers"]}

def _valid_log(**overrides):
    doc = {
        "version": 2,
        "status": "success",
        "eval": {
            "task": "flywheel_import_contract",
            "model": "mockllm/model",
            "run_id": "run-1",
            "config": {"limit": 2},
        },
        "results": {
            "total_samples": 2,
            "completed_samples": 2,
            "scores": [
                {
                    "name": "match",
                    "scorer": "match",
                    "scored_samples": 2,
                    "unscored_samples": 0,
                    "metrics": {"accuracy": {"value": 0.5}},
                }
            ],
        },
        "samples": [
            {
                "id": "s/1~β",
                "epoch": 1,
                "scores": {"grade/with~unicodeβ": {
                    "value": "C",
                    "answer": "do not copy answer",
                    "explanation": "do not copy explanation",
                }, "match": {"value": "C"}},
                "messages": [{"content": "do not copy prompt"}],
                "output": {"completion": "do not copy output"},
                "model_usage": {"total_tokens": 99},
            },
            {"id": "s2", "epoch": 1, "scores": {"match": {"value": "I"}}},
        ],
    }
    doc.update(overrides)
    return doc


def test_success_log_reports_inspect_values_without_claiming_a_pass():
    import_inspect_log, _ = _api()
    raw = _raw(_valid_log())

    doc = import_inspect_log(raw)

    assert doc["schema"] == "flywheel.inspect-evidence/v1"
    assert doc["source"] == {
        "sha256": hashlib.sha256(raw).hexdigest(),
        "byte_length": len(raw),
    }
    assert doc["producer"] == {"format": "inspect-json", "version": 2}
    assert doc["reported_status"] == "success"
    assert doc["assessment"] == "reported"
    assert doc["semantic_verification"] == "UNVERIFIABLE"
    assert "PASS" not in json.dumps(doc)
    assert doc["counts"] == {
        "total_samples": 2,
        "completed_samples": 2,
        "config_limit": 2,
        "config_limit_pointer": "/eval/config/limit",
        "observed_samples": 2,
    }
    assert doc["scoring_coverage"]["sample_score_records"] == 3
    assert doc["samples"][0] == {
        "id": "s/1~β",
        "epoch": 1,
        "status": None,
        "error": None,
        "scores": [
            {"scorer": "grade/with~unicodeβ", "value": "C"},
            {"scorer": "match", "value": "C"},
        ],
    }
    assert doc["samples"][1]["scores"] == [{"scorer": "match", "value": "I"}]

    dumped = json.dumps(doc, ensure_ascii=False)
    assert "do not copy prompt" not in dumped
    assert "do not copy output" not in dumped
    assert "do not copy answer" not in dumped
    assert "do not copy explanation" not in dumped
    assert "total_tokens" not in dumped

    pointers = _by_pointer(doc)
    assert pointers["/version"] == 2
    assert pointers["/status"] == "success"
    assert pointers["/eval/task"] == "flywheel_import_contract"
    assert pointers["/eval/model"] == "mockllm/model"
    assert pointers["/eval/run_id"] == "run-1"
    assert pointers["/results/total_samples"] == 2
    assert pointers["/results/completed_samples"] == 2
    assert pointers["/eval/config/limit"] == 2
    assert pointers["/samples/0/id"] == "s/1~β"
    assert pointers["/samples/0/epoch"] == 1
    assert pointers["/samples/0/scores/grade~1with~0unicodeβ/value"] == "C"
    assert pointers["/samples/1/scores/match/value"] == "I"
    assert pointers["/results/scores/0/scored_samples"] == 2


def test_started_log_without_samples_is_incomplete_and_does_not_invent_denominator():
    import_inspect_log, _ = _api()
    raw = _raw({
        "version": 2,
        "status": "started",
        "eval": {"task": "task", "model": "model", "run_id": "run", "config": {"max_samples": 10}},
        "results": {"total_samples": 5, "completed_samples": 1},
    })

    doc = import_inspect_log(raw)

    assert doc["assessment"] == "incomplete"
    assert doc["counts"]["total_samples"] == 5
    assert doc["counts"]["completed_samples"] == 1
    assert doc["counts"]["config_limit"] is None
    assert doc["counts"]["config_limit_pointer"] is None
    assert doc["counts"]["observed_samples"] == 0
    assert "expected_samples" not in doc["counts"]
    assert doc["scoring_coverage"]["coverage_complete"] is False


def test_error_status_without_samples_preserves_error_as_error():
    import_inspect_log, _ = _api()
    raw = _raw({
        "version": 2,
        "status": "error",
        "eval": {"task": "task", "model": "model", "run_id": "run"},
        "results": {"total_samples": 2, "completed_samples": 0},
        "error": {"message": "scorer crashed"},
    })

    doc = import_inspect_log(raw)

    assert doc["assessment"] == "error"
    assert _by_pointer(doc)["/error/message"] == "scorer crashed"


def test_success_status_with_top_level_error_is_not_reported():
    import_inspect_log, _ = _api()
    raw = _raw(_valid_log(error={"message": "late error"}))

    doc = import_inspect_log(raw)

    assert doc["reported_status"] == "success"
    assert doc["assessment"] == "error"
    assert doc["reported_error"] == {"message": "late error"}


def test_structured_score_values_are_preserved_without_payload_fields():
    import_inspect_log, _ = _api()
    raw = _raw(_valid_log(samples=[
        {
            "id": "s1",
            "epoch": 1,
            "scores": {
                "seq": {"value": ["C", 1, False]},
                "map": {"value": {"grade": "C", "confidence": None}},
            },
            "messages": [{"content": "do not copy"}],
        },
        {"id": "s2", "epoch": 1, "scores": {"match": {"value": "I"}}},
    ], results={"total_samples": 2, "completed_samples": 2}))

    doc = import_inspect_log(raw)

    assert doc["samples"][0]["scores"] == [
        {"scorer": "seq", "value": ["C", 1, False]},
        {"scorer": "map", "value": {"grade": "C", "confidence": None}},
    ]
    pointers = _by_pointer(doc)
    assert pointers["/samples/0/scores/seq/value"] == ["C", 1, False]
    assert pointers["/samples/0/scores/map/value"] == {"grade": "C", "confidence": None}
    assert "do not copy" not in json.dumps(doc)


def test_sample_errors_make_a_successful_run_incomplete_without_copying_payloads():
    import_inspect_log, _ = _api()
    sample = {"id": "s2", "epoch": 1, "status": "error", "error": {"message": "sample failed"}}
    raw = _raw(_valid_log(
        samples=[{"id": "s1", "epoch": 1}, sample],
        results={"total_samples": 2, "completed_samples": 2},
    ))

    doc = import_inspect_log(raw)

    assert doc["assessment"] == "incomplete"
    assert doc["samples"][1]["status"] == "error"
    assert doc["samples"][1]["error"] == {"message": "sample failed"}
    assert _by_pointer(doc)["/samples/1/error/message"] == "sample failed"


def test_empty_string_sample_error_still_marks_coverage_incomplete():
    import_inspect_log, _ = _api()
    raw = _raw(_valid_log(samples=[
        {"id": "s1", "epoch": 1, "error": "", "scores": {"match": {"value": "C"}}},
        {"id": "s2", "epoch": 1, "scores": {"match": {"value": "I"}}},
    ]))

    doc = import_inspect_log(raw)

    assert doc["assessment"] == "incomplete"
    assert doc["samples"][0]["error"] == ""
    assert _by_pointer(doc)["/samples/0/error"] == ""


def test_repeated_sample_ids_are_allowed_across_distinct_epochs():
    import_inspect_log, _ = _api()
    raw = _raw(_valid_log(samples=[
        {"id": "same", "epoch": 1, "scores": {"match": {"value": "C"}}},
        {"id": "same", "epoch": 2, "scores": {"match": {"value": "I"}}},
    ]))

    doc = import_inspect_log(raw)

    assert [(sample["id"], sample["epoch"]) for sample in doc["samples"]] == [
        ("same", 1),
        ("same", 2),
    ]


@pytest.mark.parametrize("bad_raw", [
    b'{"version":2,"version":2,"status":"success","eval":{},"samples":[]}',
    b'{"version":2,\xff}',
    b'[]',
    b'{"version":3,"status":"success","eval":{},"samples":[]}',
    b'{"version":true,"status":"success","eval":{},"samples":[]}',
    b'{"version":2,"status":"done","eval":{},"samples":[]}',
    b'{"version":2,"status":"success","eval":[],"samples":[]}',
    b'{"version":2,"status":"success","eval":{},"samples":{} }',
    b'{"version":2,"status":"success","eval":{},"samples":[true]}',
    b'{"version":2,"status":"success","eval":{},"samples":[],"results":{"total_samples":NaN}}',
    b'{"version":2,"status":"success","eval":{}',
])
def test_malformed_roots_types_numbers_and_truncation_are_rejected(bad_raw):
    import_inspect_log, InspectImportError = _api()

    with pytest.raises(InspectImportError):
        import_inspect_log(bad_raw)

def test_input_larger_than_sixteen_mib_is_rejected_before_import():
    import_inspect_log, InspectImportError = _api()

    with pytest.raises(InspectImportError): import_inspect_log(b" " * (16 * 1024 * 1024 + 1))


@pytest.mark.parametrize("mutator", [
    lambda doc: doc["results"].update({"total_samples": 1}),
    lambda doc: doc["results"].update({"total_samples": 2, "completed_samples": 3}),
    lambda doc: doc["results"].update({"total_samples": True}),
    lambda doc: doc["samples"].append({"id": "s2", "epoch": 1}),
    lambda doc: doc["samples"][0].update({"epoch": True}),
    lambda doc: doc["samples"][0].update({"scores": []}),
    lambda doc: doc["samples"][0]["scores"].update({"bad": {"answer": "missing value"}}),
    lambda doc: doc["samples"][0]["scores"].update({"bad": {"value": {"nested": {}}}}),
    lambda doc: doc["results"]["scores"][0].update({"scored_samples": 3}),
    lambda doc: doc["eval"]["config"].update({"limit": [1, 2, 3]}),
    lambda doc: doc["eval"]["config"].update({"limit": [1, True]}),
])
def test_stale_counts_duplicate_samples_and_malformed_scores_are_rejected(mutator):
    import_inspect_log, InspectImportError = _api()
    doc = _valid_log()
    mutator(doc)

    with pytest.raises(InspectImportError):
        import_inspect_log(_raw(doc))
