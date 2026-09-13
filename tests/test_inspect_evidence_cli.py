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
