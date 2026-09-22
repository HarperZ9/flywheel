"""Managed policy is enforced at native thread and turn boundaries."""
import importlib
import importlib.util
from pathlib import Path

import pytest

from test_codex_provider_session_runtime import Client as ConfigClient


class Client(ConfigClient):
    def __init__(self):
        super().__init__()
        self.transport = object()
        self.sent = []
        self.response = super().config_read()
        self.thread_response = {'model': 'test-model', 'modelProvider': 'openai',
            'approvalPolicy': 'on-request', 'approvalsReviewer': 'user',
            'cwd': str(Path('/synthetic').absolute()),
            'sandbox': {'type': 'readOnly', 'networkAccess': False},
            'thread': {'id': 'thread-1'}}

    def thread_start(self, **params):
        self.sent.append(('thread/start', params))
        return self.thread_response

    def thread_resume(self, thread_id, **params):
        self.sent.append(('thread/resume', {'threadId': thread_id, **params}))
        return self.thread_response

    def turn_start(self, thread_id, input, **params):
        self.sent.append(('turn/start', {'threadId': thread_id, 'input': input, **params}))
        return {'turn': {'id': 'turn-1'}}


def managed(client):
    name = 'harness.codex_managed_client'
    assert importlib.util.find_spec(name), 'Managed client missing'
    return importlib.import_module(name).ManagedCodexClient(
        client, workspace=Path('/synthetic').absolute(), model='test-model')


def test_thread_and_turn_force_reviewed_policy():
    raw = Client()
    client = managed(raw)
    client.thread_start(model='test-model')
    client.turn_start('thread-1', [{'type': 'text', 'text': 'hello'}])
    thread, turn = [row[1] for row in raw.sent]
    assert thread['approvalPolicy'] == turn['approvalPolicy'] == 'on-request'
    assert thread['approvalsReviewer'] == turn['approvalsReviewer'] == 'user'
    assert thread['sandbox'] == 'read-only'
    assert turn['sandboxPolicy'] == {'type': 'readOnly', 'networkAccess': False}
    assert thread['modelProvider'] == 'openai'
    assert thread['cwd'] == turn['cwd'] == str(Path('/synthetic').absolute())


@pytest.mark.parametrize('params', [{'sandbox': 'danger-full-access'}, {'model': 'wrong'},
    {'config': {}}, {'baseInstructions': 'override'}, {'cwd': '/other'}])
def test_caller_cannot_override_thread_policy(params):
    raw = Client()
    with pytest.raises(Exception, match='AGENT_BINDING_DRIFT'):
        managed(raw).thread_start(**params)
    assert raw.sent == []


def test_unobserved_thread_cannot_receive_input():
    raw = Client()
    with pytest.raises(Exception, match='AGENT_BINDING_DRIFT'):
        managed(raw).turn_start('unobserved', [])
    assert raw.sent == []


def test_drift_after_thread_creation_blocks_input():
    raw = Client()
    client = managed(raw)
    client.thread_start()
    raw.response['layers'][1]['version'] = 'changed-disabled-layer'
    with pytest.raises(Exception, match='AGENT_BINDING_DRIFT'):
        client.turn_start('thread-1', [])
    assert len(raw.sent) == 1


def test_provider_policy_mismatch_blocks_input():
    raw = Client()
    raw.thread_response['sandbox']['networkAccess'] = True
    client = managed(raw)
    with pytest.raises(Exception, match='AGENT_BINDING_DRIFT'):
        client.thread_start()
    with pytest.raises(Exception, match='AGENT_BINDING_DRIFT'):
        client.turn_start('thread-1', [])
    assert len(raw.sent) == 1


def test_resume_must_echo_same_thread_and_policy():
    raw = Client()
    with pytest.raises(Exception, match='AGENT_BINDING_DRIFT'):
        managed(raw).thread_resume('other-thread')


def test_requested_turn_model_cannot_change_from_bound_model():
    raw = Client()
    client = managed(raw)
    client.thread_start()
    with pytest.raises(Exception, match='AGENT_BINDING_DRIFT'):
        client.turn_start('thread-1', [], model='wrong')
    assert len(raw.sent) == 1
