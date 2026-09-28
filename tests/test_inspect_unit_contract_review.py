import hashlib

from test_inspect_unit_contract import _log, _sidecar, _verify


def test_mapped_span_must_match_adapter_observed_definition_identity():
    source = _log([1])
    sidecar = _sidecar(source)
    ref = sidecar["contracts"][0]["source_item_mapping"][0]["mapped_definitions"]["refs"][0]
    text = source["samples"][0]["output"]["completion"]
    start = text.index("result = 0")
    ref["unit_id"] = "not_a_test_definition"
    ref["source"]["span"] = {"encoding": "json-string-codepoints-v1",
                             "start": start, "end": start + len("result = 0")}
    ref["source"]["source_value"] = "result = 0"
    ref["source"]["source_value_sha256"] = hashlib.sha256(b"result = 0").hexdigest()

    unit = _verify(source, sidecar)

    contract = unit["contracts"][0]
    assert contract["mapping_consistency"]["status"] == "DRIFT"
    assert "selector_completeness_unverified" in contract["mapping_consistency"]["reason_codes"]


def test_malformed_exclusion_does_not_reconcile_omitted_definition():
    source = _log([2])
    sidecar = _sidecar(source)
    row = sidecar["contracts"][0]["source_item_mapping"][0]
    row["mapped_definitions"]["refs"] = row["mapped_definitions"]["refs"][:1]
    row["mapped_definitions"]["count"] = 1
    sidecar["contracts"][0]["exclusions"] = [{}]

    unit = _verify(source, sidecar)

    contract = unit["contracts"][0]
    assert contract["mapping_consistency"]["status"] == "DRIFT"
    reasons = contract["mapping_consistency"]["reason_codes"]
    assert "omitted_definition_without_exclusion" in reasons
    assert "selector_completeness_unverified" in reasons


def test_source_row_index_must_match_row_refs_and_named_scorer():
    source = _log([1, 1])
    sidecar = _sidecar(source)
    row = sidecar["contracts"][0]["source_item_mapping"][0]["source_row"]
    row["sample_id_ref"] = {"json_pointer": "/samples/1/id", "source_value": "batch-1"}
    row["score_ref"] = {"json_pointer": "/samples/1/scores/taxonomy/value", "source_value": "C"}

    unit = _verify(source, sidecar)

    contract = unit["contracts"][0]
    assert contract["mapping_consistency"]["status"] == "DRIFT"
    assert "source_value_mismatch" in contract["mapping_consistency"]["reason_codes"]


def test_complete_mapping_rejects_extra_unscored_source_row():
    source = _log([1, 1])
    del source["samples"][1]["scores"]["taxonomy"]
    source["results"]["scores"][0]["scored_samples"] = 1
    sidecar = _sidecar(source)
    contract = sidecar["contracts"][0]
    contract["actual_score_measure"]["cardinality"] = 1
    contract["actual_score_measure"]["source_refs"][0]["source_value"] = 1
    contract["source_item_mapping"][1]["source_row"]["score_ref"] = {
        "json_pointer": "/samples/0/scores/taxonomy/value",
        "source_value": "C",
    }

    unit = _verify(source, sidecar)

    contract = unit["contracts"][0]
    assert contract["mapping_consistency"]["status"] == "DRIFT"
    assert "source_value_mismatch" in contract["mapping_consistency"]["reason_codes"]


def test_python_adapter_rejects_coherently_relabelled_non_definition_unit():
    source = _log([2])
    sidecar = _sidecar(source)
    contract = sidecar["contracts"][0]
    contract["declared_intended_measure"]["unit"] = "sha256_hash_match"
    contract["declared_intended_measure"]["cardinality"] = 1
    contract["aggregation"]["input_unit"] = "sha256_hash_match"
    mapped = contract["source_item_mapping"][0]["mapped_definitions"]
    mapped["unit"] = "sha256_hash_match"
    mapped["refs"] = mapped["refs"][:1]
    mapped["count"] = 1

    unit = _verify(source, sidecar)

    result = unit["contracts"][0]["mapping_consistency"]
    assert result["status"] == "DRIFT"
    assert "unsupported_declared_intended_unit" in result["reason_codes"]
    assert "unsupported_mapped_definition_unit" in result["reason_codes"]
    assert "unsupported_aggregation_input_unit" in result["reason_codes"]
    assert "omitted_definition_without_exclusion" in result["reason_codes"]


def test_valid_hashes_and_counts_do_not_make_relabelled_unit_match():
    source = _log([1])
    sidecar = _sidecar(source)
    contract = sidecar["contracts"][0]
    contract["declared_intended_measure"]["unit"] = "sha256_hash_match"
    contract["aggregation"]["input_unit"] = "sha256_hash_match"
    contract["source_item_mapping"][0]["mapped_definitions"]["unit"] = "sha256_hash_match"

    unit = _verify(source, sidecar)

    result = unit["contracts"][0]["mapping_consistency"]
    assert result["status"] == "DRIFT"
    assert "unsupported_declared_intended_unit" in result["reason_codes"]
    assert "unsupported_mapped_definition_unit" in result["reason_codes"]
    assert "unsupported_aggregation_input_unit" in result["reason_codes"]


def test_exclusion_without_nonblank_reason_does_not_reconcile_omission():
    source = _log([2])
    sidecar = _sidecar(source)
    contract = sidecar["contracts"][0]
    mapped = contract["source_item_mapping"][0]["mapped_definitions"]
    excluded = mapped["refs"].pop()
    mapped["count"] = 1
    contract["exclusions"] = [{"unit_id": excluded["unit_id"],
                               "source": excluded["source"], "reason": "   "}]

    unit = _verify(source, sidecar)

    result = unit["contracts"][0]["mapping_consistency"]
    assert result["status"] == "DRIFT"
    assert "exclusion_reason_missing" in result["reason_codes"]
    assert "omitted_definition_without_exclusion" in result["reason_codes"]


def test_exclusion_with_reason_reconciles_explicitly_excluded_definition():
    source = _log([2])
    sidecar = _sidecar(source)
    contract = sidecar["contracts"][0]
    mapped = contract["source_item_mapping"][0]["mapped_definitions"]
    excluded = mapped["refs"].pop()
    mapped["count"] = 1
    contract["exclusions"] = [{"unit_id": excluded["unit_id"],
                               "source": excluded["source"], "reason": "fixture scope"}]

    unit = _verify(source, sidecar)

    assert unit["contracts"][0]["mapping_consistency"] == {"status": "MATCH", "reason_codes": []}
