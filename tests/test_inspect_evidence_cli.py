"""Packaged Inspect import must retain failure and custody boundaries."""
import json
import hashlib


def _log(status='success'):
    return {'version': 2, 'status': status,
            'eval': {'task': 'review', 'model': 'mockllm/model'},
            'results': {'total_samples': 1, 'completed_samples': 1},
            'samples': [{'id': 'one', 'epoch': 1,
                         'scores': {'match': {'value': 'I'}}}]}


def test_complete_cli_import_retains_incorrect_score_and_unverified_meaning(tmp_path, capsys):
    from harness.inspect_evidence_cli import main
    raw = json.dumps(_log()).encode('utf-8')
    source = tmp_path / 'run.json'
    source.write_bytes(raw)
    assert main([str(source), '--expected-sha256', hashlib.sha256(raw).hexdigest()]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report['semantic_verification'] == 'UNVERIFIABLE'
    assert report['samples'][0]['scores'][0]['value'] == 'I'


def test_cancelled_cli_import_remains_non_success(tmp_path, capsys):
    from harness.inspect_evidence_cli import main
    source = tmp_path / 'run.json'
    source.write_text(json.dumps(_log('cancelled')), encoding='utf-8')
    assert main([str(source)]) == 3
    assert json.loads(capsys.readouterr().out)['reported_status'] == 'cancelled'


def test_packaged_import_is_discoverable(monkeypatch):
    from harness import cli_entry
    seen = []
    class Module:
        def main(self, args):
            seen.append(args)
            return 3
    import importlib
    monkeypatch.setattr(importlib, 'import_module', lambda name: Module())
    assert cli_entry._PACKAGED['import-inspect'] == 'harness.inspect_evidence_cli'
    assert cli_entry.main(['import-inspect', 'run.json']) == 3
    assert seen == [['run.json']]


def test_binary_log_requires_official_export(tmp_path, capsys):
    from harness.inspect_evidence_cli import main
    source = tmp_path / 'run.eval'
    source.write_bytes(b'PK\x03\x04binary')
    assert main([str(source)]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result['error'] == 'INSPECT_JSON_REQUIRED'


def test_malformed_log_does_not_leak_source(tmp_path, capsys):
    from harness.inspect_evidence_cli import main
    source = tmp_path / 'run.json'
    source.write_text('PRIVATE-CONTENT-not-json')
    assert main([str(source)]) == 2
    printed = capsys.readouterr().out
    assert 'PRIVATE-CONTENT' not in printed
    assert json.loads(printed)['error'] == 'INSPECT_INPUT_REJECTED'


def test_expected_digest_rejects_changed_source(tmp_path, capsys):
    from harness.inspect_evidence_cli import main
    source = tmp_path / 'run.json'
    source.write_text('{}')
    assert main([str(source), '--expected-sha256', '0' * 64]) == 2
    assert json.loads(capsys.readouterr().out)['error'] == 'SOURCE_DIGEST_MISMATCH'


def _unit_contract_for(raw_log):
    import hashlib
    text = raw_log["samples"][0]["output"]["completion"]
    value_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    source_hash = hashlib.sha256(json.dumps(raw_log, separators=(",", ":")).encode("utf-8")).hexdigest()
    return {
        "schema": "flywheel.inspect-scorer-unit-contract/v1",
        "source": {"format": "inspect-json", "schema_version": 2,
                   "sha256": source_hash,
                   "byte_length": len(json.dumps(raw_log, separators=(",", ":")).encode("utf-8"))},
        "contracts": [{
            "scorer": {"name": "match", "result_pointer": "/results/scores/0",
                       "implementation": {"kind": "reported-or-fixture", "package": None,
                                          "version": None, "source_ref": "test", "source_sha256": None}},
            "actual_score_measure": {"unit": "inspect_sample", "cardinality": 1,
                                     "source_refs": [{"json_pointer": "/results/scores/0/scored_samples", "source_value": 1}]},
            "declared_intended_measure": {"unit": "python_test_function_definition", "cardinality": 1,
                                           "authority": "sidecar", "confidence": "fixture-declared"},
            "mapping_controls": {"coverage_scope": "complete", "omitted_policy": "forbid",
                                 "duplicate_policy": "forbid", "overlap_policy": "forbid",
                                 "selector_completeness": "complete"},
            "adapter_observations": [{"adapter": "flywheel.python-test-definition-enumerator/v1",
                                      "container_pointer": "/samples/0/output/completion",
                                      "container_value_sha256": value_hash,
                                      "observed_definitions": 1,
                                      "omitted_definitions": 0,
                                      "duplicate_definition_names": []}],
            "source_item_mapping": [{
                "source_row": {"sample_index": 0, "sample_id": "one",
                               "sample_id_ref": {"json_pointer": "/samples/0/id", "source_value": "one"},
                               "epoch_ref": {"json_pointer": "/samples/0/epoch", "source_value": 1},
                               "score_ref": {"json_pointer": "/samples/0/scores/match/value", "source_value": "I"}},
                "mapped_definitions": {"unit": "python_test_function_definition", "count": 1,
                                       "refs": [{"unit_id": "one", "source": {
                                           "container_pointer": "/samples/0/output/completion",
                                           "container_value_sha256": value_hash,
                                           "span": {"encoding": "json-string-codepoints-v1", "start": 0, "end": len(text)},
                                           "source_value": text,
                                           "source_value_sha256": value_hash}}]}}],
            "exclusions": [],
            "aggregation": {"input_unit": "python_test_function_definition", "output_unit": "inspect_sample",
                            "mode": "many_to_one", "reducer": "row score"},
        }],
    }


def test_cli_import_with_unit_contract_reports_mapping_without_score_relabelling(tmp_path, capsys):
    from harness.inspect_evidence_cli import main
    log = _log()
    log["results"]["scores"] = [
        {"name": "match", "scorer": "match", "scored_samples": 1, "unscored_samples": 0}
    ]
    log["samples"][0]["output"] = {"completion": "def test_one():\n    assert True"}
    raw = json.dumps(log, separators=(",", ":")).encode("utf-8")
    source = tmp_path / "run.json"
    sidecar = tmp_path / "run.unit.json"
    source.write_bytes(raw)
    sidecar.write_bytes(json.dumps(_unit_contract_for(log), separators=(",", ":")).encode("utf-8"))

    assert main([str(source), "--unit-contract", str(sidecar)]) == 0
    report = json.loads(capsys.readouterr().out)

    contract = report["scorer_unit_analysis"]["contracts"][0]
    assert contract["mapping_consistency"]["status"] == "MATCH"
    assert contract["score_unit_relationship"]["status"] == "many-to-one"
    assert contract["definition_score_coverage"]["status"] == "UNVERIFIABLE"
    span_ref = contract["source_item_mapping"][0]["mapped_definitions"]["refs"][0]
    assert span_ref["source"]["source_value"] == "def test_one():\n    assert True"
    assert report["samples"][0]["scores"] == [{"scorer": "match", "value": "I"}]


def test_cli_unit_contract_drift_is_not_exit_zero(tmp_path, capsys):
    from harness.inspect_evidence_cli import main
    log = _log()
    log["results"]["scores"] = [
        {"name": "match", "scorer": "match", "scored_samples": 1, "unscored_samples": 0}
    ]
    log["samples"][0]["output"] = {"completion": "def test_one():\n    assert True"}
    unit = _unit_contract_for(log)
    unit["contracts"][0]["declared_intended_measure"]["cardinality"] = 2
    source = tmp_path / "run.json"
    sidecar = tmp_path / "run.unit.json"
    source.write_bytes(json.dumps(log, separators=(",", ":")).encode("utf-8"))
    sidecar.write_bytes(json.dumps(unit, separators=(",", ":")).encode("utf-8"))

    assert main([str(source), "--unit-contract", str(sidecar)]) == 3
    report = json.loads(capsys.readouterr().out)
    assert report["scorer_unit_analysis"]["contracts"][0]["mapping_consistency"]["status"] == "DRIFT"
