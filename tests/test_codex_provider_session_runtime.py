"""False-admission controls for Codex configuration inspection."""
from copy import deepcopy
import importlib
import importlib.util
import json
import re

import pytest


def inspector():
    name = 'harness.codex_provider_session_runtime'
    assert importlib.util.find_spec(name), 'Missing runtime configuration inspector'
    return importlib.import_module(name).inspect_codex_configuration


def config_fixture():
    meta = {'name': {'type': 'sessionFlags'}, 'version': 'session-1'}
    cfg = {'model': 'test-model', 'approval_policy': 'on-request',
           'approvals_reviewer': 'user', 'sandbox_mode': 'read-only',
           'web_search': 'disabled', 'features': {'hooks': False, 'apps': False,
                                               'plugins': False},
           'mcp_servers': {}, 'notify': [], 'project_doc_max_bytes': 0}
    origins = {k: deepcopy(meta) for k in
               ('model', 'approval_policy', 'approvals_reviewer', 'sandbox_mode',
                'web_search', 'features.hooks', 'features.apps', 'features.plugins')}
    layers = [{**deepcopy(meta), 'config': deepcopy(cfg), 'disabledReason': None},
              {'name': {'type': 'project', 'dotCodexFolder': '/synthetic/.codex'},
               'version': 'project-1', 'config': {'model': 'unused'},
               'disabledReason': 'project not trusted'}]
    return {'config': cfg, 'origins': origins, 'layers': layers}


class Client:
    def __init__(self, response=None, requirements=None):
        self.response = config_fixture() if response is None else response
        self.requirements = {'requirements': None} if requirements is None else requirements
        self.calls = []

    def config_read(self, **kwargs):
        self.calls.append(('config/read', kwargs))
        return self.response

    def config_requirements_read(self):
        self.calls.append(('configRequirements/read', {}))
        return self.requirements


def inspect(client):
    return inspector()(client, cwd='/synthetic', model='test-model')


def test_complete_policy_read_is_not_runtime_admission():
    client = Client()
    result = inspect(client)
    assert result.configuration_ready is True
    assert result.admitted is False
    assert result.issues == ()
    assert re.fullmatch('[0-9a-f]{64}', result.config_digest)
    assert client.calls == [('config/read', {'cwd': '/synthetic', 'include_layers': True}),
                            ('configRequirements/read', {})]
    assert 'execution' in result.does_not_prove


def test_inherited_mcp_survives_empty_override_and_is_rejected():
    response = config_fixture()
    response['config']['mcp_servers'] = {'unreviewed': {'enabled': True, 'command': 'secret'}}
    result = inspect(Client(response))
    assert not result.configuration_ready
    assert 'external_mcp_enabled' in result.issues
    assert 'secret' not in json.dumps(result.as_result())


@pytest.mark.parametrize('key,value,issue', [
    ('model', 'different', 'model_mismatch'),
    ('approval_policy', 'never', 'approval_policy_mismatch'),
    ('approvals_reviewer', 'auto_review', 'approval_reviewer_mismatch'),
    ('sandbox_mode', 'danger-full-access', 'sandbox_mismatch'),
    ('web_search', 'live', 'web_search_enabled'),
    ('notify', ['secret-command'], 'notify_enabled'),
    ('project_doc_max_bytes', 1000, 'project_instructions_enabled'),
])
def test_effective_policy_mismatch_rejected(key, value, issue):
    response = config_fixture()
    response['config'][key] = value
    assert issue in inspect(Client(response)).issues


@pytest.mark.parametrize('feature', ['hooks', 'apps', 'plugins'])
def test_missing_or_enabled_feature_cannot_appear_disabled(feature):
    response = config_fixture()
    del response['config']['features'][feature]
    assert 'extension_policy_mismatch' in inspect(Client(response)).issues
    response['config']['features'][feature] = True
    assert 'extension_policy_mismatch' in inspect(Client(response)).issues


@pytest.mark.parametrize('malformation', ['missing_layers', 'empty_layers', 'active_project',
                                          'unknown_layer', 'missing_origin', 'stale_origin'])
def test_untrustworthy_layer_provenance_rejected(malformation):
    response = config_fixture()
    if malformation == 'missing_layers':
        del response['layers']
    elif malformation == 'empty_layers':
        response['layers'] = []
    elif malformation == 'active_project':
        response['layers'][1]['disabledReason'] = None
    elif malformation == 'unknown_layer':
        response['layers'][0]['name']['type'] = 'futureManagedLayer'
    elif malformation == 'missing_origin':
        del response['origins']['approval_policy']
    else:
        response['origins']['approval_policy']['version'] = 'unobserved-version'
    result = inspect(Client(response))
    assert not result.configuration_ready
    assert not result.admitted


def test_disabled_layer_changes_are_bound_even_without_effective_change():
    response = config_fixture()
    before = inspect(Client(response))
    response['layers'][1]['config']['model'] = 'changed-inactive-model'
    response['layers'][1]['version'] = 'project-2'
    after = inspect(Client(response))
    assert before.configuration_ready and after.configuration_ready
    assert before.config_digest != after.config_digest


@pytest.mark.parametrize('requirements', [{}, {'requirements': 'invalid'},
                                         {'requirements': {'allowManagedHooksOnly': True}}])
def test_missing_malformed_or_unreviewed_requirements_rejected(requirements):
    assert not inspect(Client(requirements=requirements)).configuration_ready


def test_provider_exception_is_sanitized_and_never_authorizes():
    class Broken(Client):
        def config_read(self, **kwargs):
            raise RuntimeError('password=do-not-publish')
    result = inspect(Broken())
    assert not result.configuration_ready
    assert not result.admitted
    assert result.config_digest == ''
    assert 'do-not-publish' not in json.dumps(result.as_result())


def test_nonfinite_config_cannot_be_hashed_as_valid_evidence():
    response = config_fixture()
    response['config']['extra'] = float('nan')
    result = inspect(Client(response))
    assert not result.configuration_ready
    assert result.config_digest == ''


@pytest.mark.parametrize('key', ['mcp_servers', 'notify', 'project_doc_max_bytes'])
def test_policy_without_origin_or_explicit_active_layer_is_rejected(key):
    response = config_fixture()
    del response['layers'][0]['config'][key]
    assert not inspect(Client(response)).configuration_ready


@pytest.mark.parametrize('key,value', [('hooks', []), ('hooks', {}),
                                      ('default_permissions', {}),
                                      ('experimental_instructions_file', '')])
def test_falsey_unreviewed_execution_settings_are_rejected(key, value):
    response = config_fixture()
    response['config'][key] = value
    assert 'unreviewed_execution_settings' in inspect(Client(response)).issues


def test_unknown_managed_response_fields_are_rejected():
    result = inspect(Client(requirements={'requirements': None, 'futurePolicy': {}}))
    assert 'managed_requirements_unreviewed' in result.issues


def test_empty_containers_with_explicit_layer_need_no_leaf_origin():
    # The installed server emits leaf origins, so empty maps/lists have none.
    response = config_fixture()
    assert 'mcp_servers' not in response['origins']
    assert inspect(Client(response)).configuration_ready


def test_disabled_layer_cannot_supply_empty_container_provenance():
    response = config_fixture()
    response['layers'][1]['config']['notify'] = response['layers'][0]['config'].pop('notify')
    assert not inspect(Client(response)).configuration_ready


def test_stale_container_origin_cannot_hide_behind_active_layer():
    response = config_fixture()
    response['origins']['notify'] = {'name': {'type': 'sessionFlags'}, 'version': 'stale'}
    assert not inspect(Client(response)).configuration_ready
