"""The packaged incident checker retains evidence failures and input custody."""
import hashlib
import json
from pathlib import Path

EXAMPLES = Path(__file__).resolve().parents[1] / 'examples/evaluation/incident-sim'


def test_cli_checks_synthetic_case_and_preserves_exact_input_hashes(capsys):
    from harness.incident_sim_cli import main
    task, trace = EXAMPLES / 'task.json', EXAMPLES / 'matching-trace.json'
    assert main(['--task', str(task), '--trace', str(trace)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report['sources']['task']['sha256'] == hashlib.sha256(task.read_bytes()).hexdigest()
    assert report['sources']['trace']['byte_length'] == len(trace.read_bytes())
    assert report['evaluation']['overall']['verdict'] == 'MATCH'
    assert report['audit_packet']


def test_cli_wrong_final_state_is_a_failure_despite_success_claim(capsys):
    from harness.incident_sim_cli import main
    assert main(['--task', str(EXAMPLES / 'task.json'),
                 '--trace', str(EXAMPLES / 'wrong-state-trace.json')]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report['evaluation']['correctness']['verdict'] == 'DRIFT'


def test_cli_rejects_byte_drift_before_interpreting_input(tmp_path, capsys):
    from harness.incident_sim_cli import main
    task, trace = tmp_path / 'task.json', tmp_path / 'trace.json'
    task.write_bytes(b'{}')
    trace.write_bytes(b'{}')
    assert main(['--task', str(task), '--trace', str(trace),
                 '--expected-task-sha256', '0' * 64]) == 2
    report = json.loads(capsys.readouterr().out)
    assert report['error'] == 'SOURCE_DIGEST_MISMATCH'


def test_cli_errors_do_not_disclose_paths_or_source_content(tmp_path, capsys):
    from harness.incident_sim_cli import main
    source = tmp_path / 'sensitive-name.json'
    source.write_bytes(b'PRIVATE-BODY-invalid-json')
    assert main(['--task', str(source), '--trace', str(source)]) == 2
    output = capsys.readouterr().out
    assert 'PRIVATE-BODY' not in output
    assert 'sensitive-name' not in output
    assert str(tmp_path) not in output
    assert json.loads(output)['error'] == 'INCIDENT_INPUT_REJECTED'


def test_cli_empty_documents_cannot_produce_a_successful_audit(tmp_path, capsys):
    from harness.incident_sim_cli import main
    source = tmp_path / 'empty.json'
    source.write_bytes(b'{}')
    assert main(['--task', str(source), '--trace', str(source)]) != 0
    assert json.loads(capsys.readouterr().out)


def test_packaged_incident_command_dispatches_without_checkout(monkeypatch):
    from harness import cli_entry
    import importlib
    seen = []
    class Module:
        def main(self, args):
            seen.append(args)
            return 1
    monkeypatch.setattr(importlib, 'import_module', lambda name: Module())
    assert cli_entry._PACKAGED['incident-sim'] == 'harness.incident_sim_cli'
    assert cli_entry.main(['incident-sim', '--task', 'case.json']) == 1
    assert seen == [['--task', 'case.json']]
