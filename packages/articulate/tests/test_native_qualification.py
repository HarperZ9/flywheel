"""False-success controls for the native qualification and provenance reader."""
import hashlib
import json
import pytest

from claude_plugin_helpers import load


@pytest.mark.parametrize('wire', [
    '', '{"jsonrpc":"2.0","id":1,"result":{},"method":"sampling/createMessage"}',
    '{"jsonrpc":"2.0","id":1,"id":2,"result":{}}',
    '{"jsonrpc":"2.0","id":true,"result":{}}',
    '{"jsonrpc":"2.0","id":1,"result":{}}\n{"jsonrpc":"2.0","id":1,"result":{}}',
])
def test_protocol_checker_rejects_ambiguous_responses(wire):
    with pytest.raises(ValueError):
        load('check_native_articulate').parse(wire, {1, 2})


def test_conflicting_tool_payload_cannot_pass():
    result = {'content': [{'type': 'text', 'text': '{"ok": true}'}],
              'structuredContent': {'ok': False}}
    with pytest.raises(ValueError, match='conflicting'):
        load('check_native_articulate').payload(result)


def test_duplicate_key_cannot_replace_a_valid_response_id():
    with pytest.raises(ValueError, match='duplicate'):
        load('check_native_articulate').parse('{"jsonrpc":"2.0","id":1,"id":2,"result":{}}', {2})


def test_native_provenance_rejects_dll_outside_runtime(tmp_path):
    runtime = tmp_path / 'python'
    runtime.mkdir()
    dll = tmp_path / 'unrelated.dll'
    dll.write_bytes(b'foreign DLL')
    toc = tmp_path / 'Analysis-00.toc'
    toc.write_text(repr(([('unrelated.dll', str(dll), 'BINARY')],)))
    with pytest.raises(ValueError, match='outside'):
        load('native_build_provenance').dependencies(toc, runtime)


def test_native_provenance_records_bytes_from_python_runtime(tmp_path):
    dll = tmp_path / 'python312.dll'
    dll.write_bytes(b'runtime fixture')
    toc = tmp_path / 'Analysis-00.toc'
    toc.write_text(repr(([('python312.dll', str(dll), 'BINARY')],)))
    records = load('native_build_provenance').dependencies(toc, tmp_path)
    assert records[0]['name'] == 'python312.dll'
    assert len(records[0]['sha256']) == 64


def test_refusal_requires_exact_local_boundary_result():
    result = {'isError': True, 'content': [{'type': 'text', 'text': json.dumps({
        'ok': False, 'error': 'network request failed after local-only enforcement was bypassed'})}]}
    with pytest.raises(ValueError):
        load('check_native_articulate').validate_refusal(result, 'fix', 'openai')


@pytest.mark.parametrize('mutation', ['backend', 'attempts', 'original_sha256', 'text_sha256'])
def test_both_submission_receipts_require_local_provenance(mutation):
    mod = load('check_native_articulate')
    digest = 'sha256:' + hashlib.sha256(mod.SOURCE.encode()).hexdigest()
    for refused in (False, True):
        receipt = {'backend': 'host', 'attempts': [], 'original_sha256': digest, 'text_sha256': digest}
        receipt[mutation] = ['openai'] if mutation == 'attempts' else 'openai'
        value = {'ok': True, 'backend': 'host', 'text': mod.SOURCE,
                 'refused': ['changed fact'] if refused else [], 'receipt': receipt}
        result = {'content': [{'type': 'text', 'text': json.dumps(value)}]}
        with pytest.raises(ValueError):
            mod.validate_submission(result, mod.SOURCE, refused)


def test_second_session_identity_is_checked():
    with pytest.raises(ValueError):
        load('check_native_articulate').validate_initialize({
            'protocolVersion': 'wrong', 'serverInfo': {'name': 'articulate', 'version': '0.5.2'}}, '0.5.2')
