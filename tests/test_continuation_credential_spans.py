"""Credential containers must not become imported task or attachment signals."""
import json

import pytest

from harness.continuation_preview import build_continuation, export_state


@pytest.mark.parametrize('name', [
    'OPENAI_API_KEY', 'GITHUB_TOKEN', 'AWS_SECRET_ACCESS_KEY',
    'accessToken', 'clientSecret', 'MYSQL_ROOT_PASSWORD',
])
def test_prefixed_or_oauth_assignment_never_enters_context(tmp_path, name):
    root = tmp_path / 'workspace'
    root.mkdir()
    export = tmp_path / 'session.txt'
    canary = 'syntheticCredentialCanary934823'
    export.write_text(f'user: Fix parser. {name}={canary} Keep tests.\n',
                      encoding='utf-8')
    preview, intake = build_continuation(root, export_path=export)
    assert canary not in json.dumps([preview, intake])
    assert 'Fix parser.' in preview['runner_context']['goal']
    assert 'Keep tests.' in preview['runner_context']['goal']
    assert any(r['code'] == 'CREDENTIAL_EXCLUDED' for r in preview['omissions'])


@pytest.mark.parametrize('terminator', ['-----END PRIVATE KEY-----\n', ''])
def test_declared_private_key_span_is_excluded_before_signal_parsing(tmp_path, terminator):
    export = tmp_path / 'session.txt'
    export.write_text('user: Preserve parser work.\n'
                      'summary: -----BEGIN PRIVATE KEY-----\n'
                      'summary: syntheticCredentialCanary934823\n'
                      'attachment: secret-path-never-probe\n' + terminator +
                      'user: Continue after key.\n', encoding='utf-8')
    state, omissions = export_state(tmp_path, export)
    assert 'syntheticCredentialCanary934823' not in json.dumps(state)
    assert not any(r['code'] == 'MISSING_ATTACHMENT' for r in omissions)
    assert any(r['code'] == 'CREDENTIAL_EXCLUDED' for r in omissions)
    texts = [r.get('text', '') for r in state['signals']]
    assert 'Preserve parser work.' in texts
    assert ('Continue after key.' in texts) is bool(terminator)
    if terminator:
        assert next(r['line'] for r in state['signals']
                    if r.get('text') == 'Continue after key.') == 6


@pytest.mark.parametrize('secret', [
    '-----BEGIN RSA PRIVATE KEY-----\n-----END EC PRIVATE KEY-----\n'
    'user: syntheticCredentialCanary934823',
    'TOKEN="first\nuser: syntheticCredentialCanary934823\\',
])
def test_malformed_or_truncated_credential_span_stays_quarantined(tmp_path, secret):
    export = tmp_path / 'session.txt'
    export.write_text('user: Work before.\nsummary: ' + secret,
                      encoding='utf-8')
    state, omissions = export_state(tmp_path, export)
    assert 'syntheticCredentialCanary934823' not in json.dumps(state)
    assert state['signals'][0]['text'] == 'Work before.'


@pytest.mark.parametrize('breaks', [('\n', '\n'), ('\r', '\n')])
def test_multiline_quoted_secret_preserves_line_numbers_and_surrounding_work(tmp_path, breaks):
    export = tmp_path / 'session.txt'
    export.write_text('user: Work before.\nsummary: TOKEN="first' + breaks[0] +
                      'user: syntheticCredentialCanary934823' + breaks[1] + 'last"\n'
                      'user: Work after.\n', encoding='utf-8', newline='')
    state, omissions = export_state(tmp_path, export)
    assert 'syntheticCredentialCanary934823' not in json.dumps(state)
    assert next(r['line'] for r in state['signals']
                if r.get('text') == 'Work after.') == 5
    assert any(r['code'] == 'CREDENTIAL_EXCLUDED' for r in omissions)
