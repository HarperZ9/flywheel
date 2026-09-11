"""Reject sampling and credential-header authority drift before any HTTP call."""
import io
import json

import pytest

from harness.gateway_agent_transport import AgentTransportError
from tests.test_gateway_agent_transport import server, transport


def request(adapter):
    if adapter == 'gemini':
        payload = {'contents': [], 'generationConfig': {
            'temperature': 0, 'maxOutputTokens': 32}}
        suffix = '/models/selected:generateContent'
        headers = {'x-goog-api-key': 'synthetic'}
    else:
        payload = {'model': 'selected', 'messages': [],
                   'max_tokens': 32, 'temperature': 0}
        suffix = '/chat/completions' if adapter == 'openai' else '/v1/messages'
        headers = ({'Authorization': 'Bearer synthetic'} if adapter == 'openai'
                   else {'x-api-key': 'synthetic', 'anthropic-version': '2023-06-01'})
    headers['Content-Type'] = 'application/json'
    return payload, suffix, headers


class Opener:
    calls = 0

    def open(self, *args, **kwargs):
        self.calls += 1
        response = io.BytesIO(b'{}')
        response.status = 200
        return response


def rejected(adapter, payload, headers, **options):
    opener = Opener()
    call = transport('http://127.0.0.1:1', adapter=adapter, opener=opener, **options)
    with pytest.raises(AgentTransportError, match='AGENT_BINDING_DRIFT'):
        call('POST', 'http://127.0.0.1:1' + request(adapter)[1], headers,
             json.dumps(payload).encode(), 3)
    assert opener.calls == call.calls == 0


@pytest.mark.parametrize('adapter', ['openai', 'anthropic', 'gemini'])
@pytest.mark.parametrize('value', [1, 0.1, -1, True, False, None, '0'])
def test_changed_or_non_numeric_temperature_is_rejected(adapter, value):
    payload, _, headers = request(adapter)
    sampling = payload['generationConfig'] if adapter == 'gemini' else payload
    sampling['temperature'] = value
    rejected(adapter, payload, headers)


@pytest.mark.parametrize('adapter', ['openai', 'anthropic', 'gemini'])
def test_missing_temperature_is_not_an_implicit_provider_default(adapter):
    payload, _, headers = request(adapter)
    sampling = payload['generationConfig'] if adapter == 'gemini' else payload
    del sampling['temperature']
    rejected(adapter, payload, headers)


@pytest.mark.parametrize('adapter', ['openai', 'anthropic', 'gemini'])
@pytest.mark.parametrize('field', ['seed', 'top_p', 'top_k', 'topP', 'topK',
                                  'frequency_penalty', 'presence_penalty'])
def test_unrequested_sampling_controls_are_rejected(adapter, field):
    payload, _, headers = request(adapter)
    sampling = payload['generationConfig'] if adapter == 'gemini' else payload
    sampling[field] = 0
    rejected(adapter, payload, headers)


@pytest.mark.parametrize('field', ['seed', 'top_p', 'temperature', 'model', 'stream'])
def test_gemini_rejects_controls_outside_generation_config(field):
    payload, _, headers = request('gemini')
    payload[field] = 0
    rejected('gemini', payload, headers)


@pytest.mark.parametrize('adapter,field', [
    ('openai', 'x-api-key'), ('openai', 'x-goog-api-key'),
    ('openai', 'anthropic-version'), ('anthropic', 'Authorization'),
    ('anthropic', 'x-goog-api-key'), ('anthropic', 'anthropic-beta'),
    ('gemini', 'Authorization'), ('gemini', 'x-api-key'),
    ('gemini', 'anthropic-version'),
])
def test_cross_provider_auth_and_capability_headers_are_rejected(adapter, field):
    payload, _, headers = request(adapter)
    headers[field] = 'synthetic'
    rejected(adapter, payload, headers)


@pytest.mark.parametrize('adapter', ['openai', 'anthropic', 'gemini'])
@pytest.mark.parametrize('content_type', [None, '', 'text/plain',
                                         'application/json; charset=utf-8'])
def test_content_type_must_match_backend_json_contract(adapter, content_type):
    payload, _, headers = request(adapter)
    del headers['Content-Type']
    if content_type is not None:
        headers['Content-Type'] = content_type
    rejected(adapter, payload, headers)


@pytest.mark.parametrize('adapter', ['openai', 'gemini'])
def test_temperature_omission_flag_cannot_expand_other_adapters(adapter):
    with pytest.raises(AgentTransportError, match='AGENT_BINDING_DRIFT'):
        transport('http://127.0.0.1:1', adapter=adapter, allow_omitted_temperature=True)


@pytest.mark.parametrize('flag', [0, 1, None, 'true'])
def test_temperature_omission_policy_is_strict_boolean(flag):
    with pytest.raises(AgentTransportError, match='AGENT_BINDING_DRIFT'):
        transport('http://127.0.0.1:1', adapter='anthropic', allow_omitted_temperature=flag)


def test_anthropic_omitted_temperature_requires_frozen_permission_and_keeps_cap():
    payload, suffix, headers = request('anthropic')
    del payload['temperature']
    rejected('anthropic', payload, headers, allow_omitted_temperature=False)
    with server() as (origin, requests):
        call = transport(origin, adapter='anthropic', allow_omitted_temperature=True)
        assert call('POST', origin + suffix, headers, json.dumps(payload).encode(), 3)[0] == 200
        actual = json.loads(requests[0][2])
        assert 'temperature' not in actual and actual['max_tokens'] == 32
    payload['max_tokens'] = 33
    rejected('anthropic', payload, headers, allow_omitted_temperature=True)


@pytest.mark.parametrize('adapter', ['openai', 'anthropic', 'gemini'])
@pytest.mark.parametrize('temperature', [0, 0.0])
def test_exact_numeric_zero_and_real_adapter_headers_are_accepted(adapter, temperature):
    payload, suffix, headers = request(adapter)
    sampling = payload['generationConfig'] if adapter == 'gemini' else payload
    sampling['temperature'] = temperature
    opener = Opener()
    call = transport('http://127.0.0.1:1', adapter=adapter, opener=opener)
    assert call('POST', 'http://127.0.0.1:1' + suffix, headers,
                json.dumps(payload).encode(), 3) == (200, {})
    assert opener.calls == call.calls == 1
