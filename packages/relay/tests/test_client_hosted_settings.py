"""The client adapter takes hosted-model credentials from its own launch settings.

An API key, gateway URL or model name set in the environment that starts the
client never reaches the online tiers. Only the provider named at launch, with
the key passed in RELAY_API_KEY, does. Health checks for hosted tiers test key
presence and send nothing, so these runs stay hermetic.
"""
import json

import pytest

from test_client_package import invoke, packaged, request  # noqa: F401 (fixture)

AMBIENT = {'OPENAI_API_KEY': 'synthetic-ambient', 'ANTHROPIC_API_KEY': 'synthetic-ambient',
           'DEEPSEEK_PROVIDER_BASE_URL': 'http://127.0.0.1:9/v1', 'GLM_CLOUD_BASE_URL': 'http://127.0.0.1:9/v1',
           'GEMINI_API_KEY': 'synthetic-ambient'}


def online_tiers(packaged, tmp_path, args=(), env=None):
    p = invoke(packaged / 'server/serve.py', tmp_path,
               [request(1, 'tools/call', name='local_agent_health', arguments={'online': True})],
               extra_env={**AMBIENT, **(env or {})}, args=list(args))
    assert p.returncode == 0, p.stderr
    body = json.loads(json.loads(p.stdout)['result']['content'][0]['text'])
    return {t['backend']: t for t in body['tiers'] if t['backend'] not in ('serve', 'ollama')}


def test_ambient_credentials_and_gateways_are_ignored(packaged, tmp_path):
    assert online_tiers(packaged, tmp_path) == {}


def test_unfilled_placeholders_mean_no_hosted_provider(packaged, tmp_path):
    args = ['--api-provider=${user_config.api_provider}', '--api-base-url=${user_config.api_base_url}',
            '--api-model=${user_config.api_model}']
    assert online_tiers(packaged, tmp_path, args, {'RELAY_API_KEY': '${user_config.api_key}'}) == {}
    assert online_tiers(packaged, tmp_path, ['--api-provider=', '--api-base-url=', '--api-model='],
                        {'RELAY_API_KEY': ''}) == {}


def test_configured_provider_uses_only_the_configured_key(packaged, tmp_path):
    tiers = online_tiers(packaged, tmp_path, ['--api-provider=deepseek', '--api-model=synthetic-model'],
                         {'RELAY_API_KEY': 'synthetic-configured'})
    assert list(tiers) == ['deepseek'] and tiers['deepseek']['healthy']
    assert tiers['deepseek']['detail'] == 'synthetic-model'


def test_provider_without_key_stays_off(packaged, tmp_path):
    assert online_tiers(packaged, tmp_path, ['--api-provider=codex'], {'RELAY_API_KEY': ''}) == {}


def test_gateway_receives_the_key_instead_of_the_official_api(packaged, tmp_path):
    tiers = online_tiers(packaged, tmp_path, ['--api-provider=claude', '--api-base-url=http://127.0.0.1:9/v1'],
                         {'RELAY_API_KEY': 'synthetic-configured'})
    assert list(tiers) == ['claude-provider']


@pytest.mark.parametrize('args', [['--api-provider=openai'], ['--api-base-url=http://127.0.0.1:9/v1'],
                                  ['--api-provider=codex', '--api-base-url=file:///synthetic'],
                                  ['--api-model=synthetic-model']])
def test_malformed_hosted_settings_stop_startup(packaged, tmp_path, args):
    p = invoke(packaged / 'server/serve.py', tmp_path, [], args=args)
    assert p.returncode != 0 and not p.stdout
