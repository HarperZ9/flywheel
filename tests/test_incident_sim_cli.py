"""The packaged incident checker retains evidence failures and input custody."""
import hashlib
import json
from pathlib import Path

EXAMPLES = Path(__file__).resolve().parents[1] / 'examples/evaluation/incident-sim'


def _write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')


def _access_scope(task, trace):
    from harness.institutional_access import access_scope
    return access_scope('incident-sim-synthetic', {'claim-final-state': ['task', 'trace']},
                        {'task': task, 'trace': trace})


def _access_record(scope_doc, task, trace):
    return {
        'schema': 'flywheel.institutional-access/v1',
        'scope_sha256': scope_doc['scope_sha256'],
        'reviewer': {
            'role': 'external_evaluator',
            'declared_conflicts': [],
            'relationship_to_producer': 'unknown',
        },
        'events': [
            {
                'event_id': 'task-grant',
                'sequence': 1,
                'evidence_ref': 'task',
                'status': 'granted',
                'stated_reason': 'synthetic fixture declared access',
                'source_pointers': [{
                    'source_ref': 'task',
                    'json_pointer': '/expected_final_state',
                    'source_value': task['expected_final_state'],
                }],
                'redactions': [],
            },
            {
                'event_id': 'trace-grant',
                'sequence': 2,
                'evidence_ref': 'trace',
                'status': 'granted',
                'stated_reason': 'synthetic fixture declared access',
                'source_pointers': [{
                    'source_ref': 'trace',
                    'json_pointer': '/final_state',
                    'source_value': trace['final_state'],
                }],
                'redactions': [],
            },
        ],
    }


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


def test_cli_attaches_complete_institutional_access_component(tmp_path, capsys):
    from harness.incident_sim_cli import main
    task_path, trace_path = EXAMPLES / 'task.json', EXAMPLES / 'matching-trace.json'
    task, trace = json.loads(task_path.read_text()), json.loads(trace_path.read_text())
    scope_doc = _access_scope(task, trace)
    access_doc = _access_record(scope_doc, task, trace)
    scope_path, access_path = tmp_path / 'scope.json', tmp_path / 'access.json'
    _write_json(scope_path, scope_doc)
    _write_json(access_path, access_doc)

    assert main(['--task', str(task_path), '--trace', str(trace_path),
                 '--institutional-access', str(access_path),
                 '--institutional-access-scope', str(scope_path)]) == 0

    report = json.loads(capsys.readouterr().out)
    component = report['audit_packet']['institutional_access']
    assert component['assessment']['coverage_assessment'] == 'complete'
    assert report['audit_packet']['packet_sha256']


def test_cli_rejects_unpaired_institutional_access_input(tmp_path, capsys):
    from harness.incident_sim_cli import main
    access_path = tmp_path / 'access.json'
    access_path.write_text('{}', encoding='utf-8')

    assert main(['--task', str(EXAMPLES / 'task.json'),
                 '--trace', str(EXAMPLES / 'matching-trace.json'),
                 '--institutional-access', str(access_path)]) == 2

    assert json.loads(capsys.readouterr().out)['error'] == 'INSTITUTIONAL_ACCESS_PAIR_REQUIRED'


def test_cli_verify_packet_roundtrip_and_tamper(tmp_path, capsys):
    from harness.incident_sim_cli import main
    packet_path = tmp_path / 'packet.json'

    assert main(['--task', str(EXAMPLES / 'task.json'),
                 '--trace', str(EXAMPLES / 'matching-trace.json')]) == 0
    packet = json.loads(capsys.readouterr().out)['audit_packet']
    _write_json(packet_path, packet)

    assert main(['--verify-packet', str(packet_path)]) == 0
    verify_report = json.loads(capsys.readouterr().out)
    assert verify_report['verification']['verdict'] == 'MATCH'
    assert verify_report['verification']['institutional_access_verdict'] == 'NOT_ASSESSED'

    packet['evaluation']['overall']['verdict'] = 'FORGED'
    _write_json(packet_path, packet)

    assert main(['--verify-packet', str(packet_path)]) == 1
    tamper_report = json.loads(capsys.readouterr().out)
    assert tamper_report['verification']['verdict'] == 'DRIFT'
    assert tamper_report['verification']['evaluation_digest_verdict'] == 'DRIFT'


def test_cli_verify_packet_accepts_key_sorted_json_serialization(tmp_path, capsys):
    from harness.incident_sim_cli import main
    from harness.incident_sim_packet import verify_process_audit_packet
    packet_path = tmp_path / 'packet.json'

    assert main(['--task', str(EXAMPLES / 'task.json'),
                 '--trace', str(EXAMPLES / 'matching-trace.json')]) == 0
    packet = json.loads(capsys.readouterr().out)['audit_packet']
    sorted_packet = json.loads(json.dumps(packet, sort_keys=True))
    packet_path.write_text(json.dumps(sorted_packet, sort_keys=True), encoding='utf-8')

    assert main(['--verify-packet', str(packet_path)]) == 0
    cli_verification = json.loads(capsys.readouterr().out)['verification']
    direct_verification = verify_process_audit_packet(sorted_packet)
    assert cli_verification['verdict'] == 'MATCH'
    assert direct_verification['verdict'] == cli_verification['verdict']
    assert direct_verification['action_chain_verdict'] == cli_verification['action_chain_verdict']


def test_cli_rejects_verify_packet_with_build_inputs(capsys):
    from harness.incident_sim_cli import main

    assert main(['--verify-packet', str(EXAMPLES / 'task.json'),
                 '--task', str(EXAMPLES / 'task.json'),
                 '--trace', str(EXAMPLES / 'matching-trace.json')]) == 2

    assert json.loads(capsys.readouterr().out)['error'] == 'CONFLICTING_OPTIONS'


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
