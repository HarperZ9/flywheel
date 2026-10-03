"""Enforce the reviewed Codex policy at thread and input boundaries."""
from __future__ import annotations

from pathlib import Path

from .codex_provider_session_runtime import inspect_codex_configuration
from .provider_session_contract import ProviderSessionError


class ManagedCodexClient:
    def __init__(self, client, *, workspace: Path, model: str):
        self._client, self.workspace, self.model = client, Path(workspace), model
        self.transport = client.transport
        self._threads: set[str] = set()
        self._failed = False
        inspection = inspect_codex_configuration(client, cwd=str(workspace), model=model)
        if not inspection.configuration_ready:
            raise ProviderSessionError('AGENT_NATIVE_RUNTIME_DISABLED')
        self.config_digest = inspection.config_digest

    def check_configuration(self):
        if self._failed:
            raise ProviderSessionError('AGENT_BINDING_DRIFT')
        current = inspect_codex_configuration(self._client, cwd=str(self.workspace),
                                             model=self.model)
        if not current.configuration_ready or current.config_digest != self.config_digest:
            self._fail()
        return current

    def thread_start(self, **params):
        options = self._thread_options(params)
        response = self._client.thread_start(**options)
        self._observe_thread(response)
        return response

    def thread_resume(self, thread_id, **params):
        options = self._thread_options(params)
        response = self._client.thread_resume(thread_id, **options)
        self._observe_thread(response, expected=thread_id)
        return response

    def turn_start(self, thread_id, input, *, client_user_message_id=None, **params):
        self._model_only(params)
        self.check_configuration()
        if thread_id not in self._threads:
            self._fail()
        return self._client.turn_start(thread_id, input,
            client_user_message_id=client_user_message_id, model=self.model,
            cwd=str(self.workspace), approvalPolicy='on-request', approvalsReviewer='user',
            sandboxPolicy={'type': 'readOnly', 'networkAccess': False})

    def turn_interrupt(self, thread_id, turn_id):
        # Interrupt remains available even if policy inspection has drifted.
        if thread_id not in self._threads:
            raise ProviderSessionError('AGENT_BINDING_DRIFT')
        return self._client.turn_interrupt(thread_id, turn_id)

    def thread_read(self, thread_id, *, include_turns=None):
        self.check_configuration()
        return self._client.thread_read(thread_id, include_turns=include_turns)

    def thread_unsubscribe(self, thread_id):
        result = self._client.thread_unsubscribe(thread_id)
        self._threads.discard(thread_id)
        return result

    def _thread_options(self, params):
        self._model_only(params)
        self.check_configuration()
        return {'model': self.model, 'modelProvider': 'openai', 'cwd': str(self.workspace),
                'approvalPolicy': 'on-request', 'approvalsReviewer': 'user',
                'sandbox': 'read-only'}

    def _model_only(self, params):
        if set(params) - {'model'} or params.get('model', self.model) != self.model:
            self._fail()

    def _observe_thread(self, response, *, expected=None):
        try:
            thread_id = response['thread']['id']
            valid = (type(thread_id) is str and bool(thread_id)
                and (expected is None or thread_id == expected)
                and response['model'] == self.model
                and response['modelProvider'] == 'openai'
                and response['approvalPolicy'] == 'on-request'
                and response['approvalsReviewer'] == 'user'
                and Path(response['cwd']) == self.workspace
                and response['sandbox'] == {'type': 'readOnly', 'networkAccess': False})
        except (KeyError, TypeError, ValueError):
            valid = False
        if not valid:
            self._fail()
        self._threads.add(thread_id)

    def _fail(self):
        self._failed = True
        raise ProviderSessionError('AGENT_BINDING_DRIFT')
