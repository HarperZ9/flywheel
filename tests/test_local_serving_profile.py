import json

import pytest

from harness.local_agent import LocalAgent, OllamaBackend
from scripts.run_model_endpoint_gate import probe_profile
from scripts.run_model_endpoint_profiles import build_report


def transport(calls):
    def run(method, url, body, timeout):
        if method == 'GET':
            return 200, {'models': [{'name': 'coder:32b', 'digest': 'a' * 64}]}
        payload = json.loads(body)
        calls.append(payload)
        return 200, {'model': payload['model'], 'message': {'content': 'same answer'}}
    return run


@pytest.mark.parametrize('streaming', [False, True])
def test_context_is_sent_and_binds_identical_answer_receipt(streaming):
    receipts = []
    for context in (4096, 8192):
        calls = []
        def stream(body):
            calls.append(json.loads(body))
            yield {'model': 'coder:32b', 'message': {'content': 'same answer'}}
            yield {'model': 'coder:32b', 'done': True}
        backend = OllamaBackend(model='coder:32b', num_ctx=context,
                                transport=transport(calls), stream_transport=stream)
        agent = LocalAgent(backends=[backend], prefer='ollama')
        result = agent.stream('hello', lambda _: None) if streaming else agent.send('hello')
        assert calls[0]['options']['num_ctx'] == context
        assert result['generation_config']['num_ctx'] == context
        receipts.append(result['x_receipt']['request_hash'])
    assert receipts[0] != receipts[1], 'Serving context must be bound even when output is identical'


@pytest.mark.parametrize('bad', [0, -1, True, '8192', 1.5, 1048577])
def test_invalid_context_rejected_before_transport(bad):
    calls = []
    with pytest.raises(ValueError, match='num_ctx'):
        OllamaBackend(model='coder:32b', num_ctx=bad, transport=transport(calls))
    assert calls == []


def test_legacy_omitted_context_does_not_claim_server_setting():
    calls = []
    backend = OllamaBackend(model='coder:32b', transport=transport(calls))
    result = backend.chat([], system='', max_tokens=32, temperature=0, seed=0)
    assert 'num_ctx' not in calls[0]['options']
    assert 'num_ctx' not in result['generation_config']


def test_generated_profiles_pin_context_and_exact_base_variant(tmp_path):
    report = build_report(models=['32B'], base_root=tmp_path, serve_url='',
                          ollama_url='http://127.0.0.1:11434', ollama_num_ctx=8192,
                          ollama_models={'32b': 'qwen2.5-coder:32b-instruct-q4_K_M'})
    base, release = [p for p in report['profiles'] if p['backend'] == 'ollama']
    assert base['selectors'][0] == 'qwen2.5-coder:32b-instruct-q4_K_M'
    assert base['model_ref'] == 'ollama:qwen2.5-coder:32b-instruct-q4_K_M'
    assert base['generation_config'] == release['generation_config'] == {'num_ctx': 8192}
    assert report['summary']['live_probed'] is False


def test_endpoint_gate_consumes_profile_context_and_records_sent_options():
    calls = []
    profile = {'profile_id': 'local', 'backend': 'ollama', 'model': '32B',
               'endpoint_url': 'http://127.0.0.1:11434', 'selectors': ['coder:32b'],
               'model_ref': 'ollama:coder:32b', 'generation_config': {'num_ctx': 8192}}
    row = probe_profile(profile, prompt='hello', timeout_seconds=1, max_tokens=32,
                        seed=7, transport=transport(calls))
    assert row['generation_ok'] is True
    assert calls[0]['options']['num_ctx'] == 8192
    assert row['generation_config'] == calls[0]['options']


def test_cross_harness_adapter_carries_context_to_same_backend():
    from harness.cross_harness_adapters import _backend
    backend = _backend({'backend': 'ollama', 'endpoint_url': 'http://127.0.0.1:11434',
                        'model_ref': 'ollama:coder:32b',
                        'generation_config': {'num_ctx': 8192}}, 20)
    assert backend.num_ctx == 8192


@pytest.mark.parametrize('config', [None, [], {'num_ctx': False}, {'num_ctx': 0}, {'num_ctx': 8192, 'typo': 1}])
def test_bad_profile_config_is_typed_failure_without_transport(config):
    from harness.cross_harness_adapters import _profile_error
    calls = []
    profile = {'profile_id': 'local', 'backend': 'ollama', 'model_ref': 'ollama:coder:32b',
               'endpoint_url': 'http://127.0.0.1:11434', 'generation_config': config}
    row = probe_profile(profile, prompt='hello', timeout_seconds=1, max_tokens=32,
                        seed=7, transport=transport(calls))
    assert row['failure_class'] == 'invalid_generation_config'
    assert row['generation_attempted'] is False
    assert row['quality_score'] == 0 and row['receipt_hash']
    assert _profile_error(profile) == 'invalid_generation_config'
    assert calls == []


def test_stream_callback_cannot_relabel_request_context():
    calls = []
    def stream(body):
        calls.append(json.loads(body))
        yield {'model': 'coder:32b', 'message': {'content': 'same answer'}}
        yield {'model': 'coder:32b', 'done': True}
    backend = OllamaBackend(model='coder:32b', num_ctx=8192,
                            transport=transport(calls), stream_transport=stream)
    result = LocalAgent(backends=[backend], prefer='ollama').stream(
        'hello', lambda _: setattr(backend, 'num_ctx', 32768))
    assert backend.num_ctx == 32768
    assert result['generation_config'] == calls[0]['options']
    assert result['generation_config']['num_ctx'] == 8192


@pytest.mark.parametrize('module,flag', [('harness.local_agent_cli', '--num-ctx'),
                                      ('scripts.run_model_endpoint_profiles', '--ollama-num-ctx')])
def test_cli_rejects_invalid_context_before_probing(module, flag, capsys):
    from importlib import import_module
    with pytest.raises(SystemExit) as failure:
        import_module(module).main([flag, '0'])
    assert failure.value.code == 2
    assert 'Traceback' not in capsys.readouterr().err
