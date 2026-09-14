import ast
import hashlib
import json


def _raw(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _defs(prefix, count):
    return "\n\n".join(
        f"def test_{prefix}_{i}():\n    result = {i}\n    assert result == {i}"
        for i in range(count)
    )


def _definition_refs(text):
    refs = []
    for node in ast.parse(text).body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not node.name.startswith("test_"):
            continue
        starts = []
        offset = 0
        for line in text.splitlines(keepends=True):
            starts.append(offset)
            offset += len(line)
        start = starts[node.lineno - 1] + node.col_offset
        end = starts[node.end_lineno - 1] + node.end_col_offset
        value = text[start:end]
        refs.append({
            "unit_id": node.name.removeprefix("test_"),
            "source": {
                "span": {"encoding": "json-string-codepoints-v1", "start": start, "end": end},
                "source_value": value,
                "source_value_sha256": hashlib.sha256(value.encode("utf-8")).hexdigest(),
            },
        })
    return refs


def _log(counts):
    samples = []
    for index, count in enumerate(counts):
        samples.append({
            "id": f"batch-{index}",
            "epoch": 1,
            "output": {"completion": _defs(f"t{index}", count)},
            "scores": {"taxonomy": {"value": "C"}},
        })
    return {
        "version": 2,
        "status": "success",
        "eval": {"task": "unit-contract", "model": "mockllm/model"},
        "results": {"total_samples": len(samples), "completed_samples": len(samples),
                    "scores": [{"name": "taxonomy", "scorer": "taxonomy",
                                "scored_samples": len(samples), "unscored_samples": 0}]},
        "samples": samples,
    }


def _sidecar(source, *, declared=None, omit_last=False, actual_count=None,
             coverage_scope="complete", aggregation=True):
    raw = _raw(source)
    items = []
    observations = []
    total_defs = 0
    for index, sample in enumerate(source["samples"]):
        pointer = f"/samples/{index}/output/completion"
        text = sample["output"]["completion"]
        refs = _definition_refs(text)
        if omit_last and index == len(source["samples"]) - 1:
            refs = refs[:-1]
        for ref in refs:
            ref["source"]["container_pointer"] = pointer
            ref["source"]["container_value_sha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
        total_defs += len(refs)
        observations.append({
            "adapter": "flywheel.python-test-definition-enumerator/v1",
            "container_pointer": pointer,
            "container_value_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "observed_definitions": len(_definition_refs(text)),
            "omitted_definitions": 0,
            "duplicate_definition_names": [],
        })
        items.append({
            "source_row": {
                "sample_index": index,
                "sample_id": sample["id"],
                "sample_id_ref": {"json_pointer": f"/samples/{index}/id", "source_value": sample["id"]},
                "epoch_ref": {"json_pointer": f"/samples/{index}/epoch", "source_value": 1},
                "score_ref": {"json_pointer": f"/samples/{index}/scores/taxonomy/value", "source_value": "C"},
            },
            "mapped_definitions": {
                "unit": "python_test_function_definition",
                "count": len(refs),
                "refs": refs,
            },
        })
    actual = len(source["samples"]) if actual_count is None else actual_count
    return {
        "schema": "flywheel.inspect-scorer-unit-contract/v1",
        "source": {"format": "inspect-json", "schema_version": 2,
                   "sha256": hashlib.sha256(raw).hexdigest(), "byte_length": len(raw)},
        "contracts": [{
            "scorer": {"name": "taxonomy", "result_pointer": "/results/scores/0",
                       "implementation": {"kind": "reported-or-fixture", "package": None,
                                          "version": None, "source_ref": "synthetic",
                                          "source_sha256": None}},
            "actual_score_measure": {"unit": "inspect_sample", "cardinality": actual,
                                     "source_refs": [{"json_pointer": "/results/scores/0/scored_samples",
                                                       "source_value": len(source["samples"])}]},
            "declared_intended_measure": {"unit": "python_test_function_definition",
                                           "cardinality": total_defs if declared is None else declared,
                                           "authority": "sidecar", "confidence": "fixture-declared"},
            "mapping_controls": {"coverage_scope": coverage_scope, "omitted_policy": "forbid",
                                 "duplicate_policy": "forbid", "overlap_policy": "forbid",
                                 "selector_completeness": "complete"},
            "adapter_observations": observations,
            "source_item_mapping": items,
            "exclusions": [],
            **({"aggregation": {"input_unit": "python_test_function_definition",
                                 "output_unit": "inspect_sample", "mode": "many_to_one",
                                 "reducer": "any_member_marks_row_C"}} if aggregation else {}),
        }],
    }


def _verify(source, sidecar=None, *, include=False):
    from harness.inspect_evidence import import_inspect_log_with_unit_contract
    raw = _raw(source)
    unit_raw = None if sidecar is None else _raw(sidecar)
    return import_inspect_log_with_unit_contract(
        raw, unit_raw, include_unverifiable_unit=include)["scorer_unit_analysis"]


def test_legacy_no_sidecar_can_report_unverifiable_unit_without_changing_sample_coverage():
    from harness.inspect_evidence import import_inspect_log, import_inspect_log_with_unit_contract
    source = _log([1, 1])

    legacy = import_inspect_log(_raw(source))
    explicit = import_inspect_log_with_unit_contract(
        _raw(source), include_unverifiable_unit=True)

    assert "scorer_unit_analysis" not in legacy
    unit = explicit["scorer_unit_analysis"]
    assert explicit["scoring_coverage"]["coverage_complete"] is True
    assert unit["reason_codes"] == ["no_unit_contract"]
    assert unit["contracts"] == []


def test_ten_inspect_rows_can_legitimately_map_to_556_definitions_without_relabelling_scores():
    counts = [56] * 6 + [55] * 4
    source = _log(counts)

    unit = _verify(source, _sidecar(source))

    contract = unit["contracts"][0]
    assert contract["mapping_consistency"] == {"status": "MATCH", "reason_codes": []}
    assert contract["score_unit_relationship"]["status"] == "many-to-one"
    assert contract["definition_score_coverage"]["status"] == "UNVERIFIABLE"
    assert contract["source_rows"] == 10
    assert contract["mapped_definitions"] == 556
    assert contract["actual_score_cardinality"] == 10
    assert contract["declared_intended_cardinality"] == 556
    first_ref = contract["source_item_mapping"][0]["mapped_definitions"]["refs"][0]
    assert first_ref["source"]["source_value"].startswith("def test_t0_0")


def test_wrong_definition_count_drifts_even_when_sample_scores_are_complete():
    source = _log([2, 3])

    unit = _verify(source, _sidecar(source, declared=4))

    contract = unit["contracts"][0]
    assert contract["mapping_consistency"]["status"] == "DRIFT"
    assert "selector_completeness_unverified" in contract["mapping_consistency"]["reason_codes"]


def test_hidden_omitted_definition_drifts_under_complete_forbid_policy():
    source = _log([2, 3])

    unit = _verify(source, _sidecar(source, omit_last=True))

    contract = unit["contracts"][0]
    assert contract["mapping_consistency"]["status"] == "DRIFT"
    assert "omitted_definition_without_exclusion" in contract["mapping_consistency"]["reason_codes"]


def test_source_value_drift_rejects_sidecar_pointer_binding():
    source = _log([1])
    sidecar = _sidecar(source)
    source["samples"][0]["id"] = "batch-renamed"
    sidecar["source"]["sha256"] = hashlib.sha256(_raw(source)).hexdigest()
    sidecar["source"]["byte_length"] = len(_raw(source))

    unit = _verify(source, sidecar)

    contract = unit["contracts"][0]
    assert contract["mapping_consistency"]["status"] == "DRIFT"
    assert "source_value_mismatch" in contract["mapping_consistency"]["reason_codes"]


def test_definition_claim_backed_only_by_scored_samples_cannot_match():
    source = _log([2, 3])
    sidecar = _sidecar(source)
    sidecar["contracts"][0]["source_item_mapping"] = []
    sidecar["contracts"][0]["adapter_observations"] = []

    unit = _verify(source, sidecar)

    contract = unit["contracts"][0]
    assert contract["mapping_consistency"]["status"] == "DRIFT"
    assert "claimed_intended_unit_backed_only_by_sample_count" in contract["mapping_consistency"]["reason_codes"]
    assert contract["definition_score_coverage"]["status"] == "UNVERIFIABLE"


def test_complete_mapping_must_cover_every_scored_row_for_named_scorer():
    source = _log([1, 1])
    sidecar = _sidecar(source)
    sidecar["contracts"][0]["source_item_mapping"].pop()

    unit = _verify(source, sidecar)

    contract = unit["contracts"][0]
    assert contract["mapping_consistency"]["status"] == "DRIFT"
    assert "omitted_definition_without_exclusion" in contract["mapping_consistency"]["reason_codes"]


def test_duplicate_unit_id_and_overlapping_selector_drift():
    source = _log([3])
    sidecar = _sidecar(source)
    refs = sidecar["contracts"][0]["source_item_mapping"][0]["mapped_definitions"]["refs"]
    refs[1]["unit_id"] = refs[0]["unit_id"]
    refs[2]["source"]["span"] = dict(refs[0]["source"]["span"])
    refs[2]["source"]["source_value"] = refs[0]["source"]["source_value"]
    refs[2]["source"]["source_value_sha256"] = refs[0]["source"]["source_value_sha256"]

    unit = _verify(source, sidecar)

    reasons = unit["contracts"][0]["mapping_consistency"]["reason_codes"]
    assert "duplicate_unit_id" in reasons
    assert "overlapping_selector" in reasons
