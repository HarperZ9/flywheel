"""Account API facade over an already initialized, owned Codex session.

This facade does not launch, authenticate, load credentials, or admit a runtime.
Its factory must bind the managed profile to the authenticated gateway owner.
"""
from __future__ import annotations

import threading

from .codex_app_server_client import CodexAppServerClient
from .codex_session_types import CodexNotification
from .provider_session_contract import ProviderSessionError

_METHODS = frozenset({
    'account/read', 'account/login/start', 'account/login/cancel',
    'account/logout', 'model/list', 'modelProvider/capabilities/read',
})


class ManagedCodexAccountClient(CodexAppServerClient):
    def __init__(self, session):
        super().__init__(_ManagedAccountTransport(session))

    @classmethod
    def connect(cls, **_kwargs):
        # The inherited convenience factory starts an ambient-profile process.
        raise ProviderSessionError('AGENT_NATIVE_MANAGED_SESSION_REQUIRED')

    def cleanup_evidence(self) -> dict[str, bool]:
        return self.transport.cleanup_evidence()


class _ManagedAccountTransport:
    def __init__(self, session):
        self._session = session
        self._closing = False
        self._closed = False
        self._lock = threading.RLock()

    def request(self, method, params=None):
        with self._lock:
            self._require_open()
            if method not in _METHODS:
                raise ProviderSessionError('AGENT_NATIVE_PROTOCOL_ERROR')
            if method != 'account/login/cancel':
                self._session.client.check_configuration()
            return self._session.transport.request(method, params)

    def pop_notification(self, *, timeout=0.0):
        with self._lock:
            self._require_open()
            item = self._session.transport.pop_notification(timeout=timeout)
            if item is None:
                return None
            if not isinstance(item, CodexNotification):
                raise ProviderSessionError('AGENT_NATIVE_PROTOCOL_ERROR')
            return {'method': item.method, 'params': item.params}

    def notification_overflowed(self):
        return self._session.transport.notification_overflowed()

    def close(self):
        with self._lock:
            if self._closed:
                return
            self._closing = True
            if not self._session.close():
                raise ProviderSessionError('AGENT_NATIVE_CLEANUP_REQUIRED')
            self._closed = True

    def cleanup_evidence(self) -> dict[str, bool]:
        with self._lock:
            cleanup = getattr(self._session, 'cleanup', None)
            transport = getattr(self._session, 'transport', None)
            if (not self._closed or getattr(self._session, 'closed', False) is not True
                    or getattr(transport, 'closed', None) is not True):
                raise ProviderSessionError('AGENT_NATIVE_CLEANUP_REQUIRED')
            evidence = {'session_closed': True, 'transport_closed': True}
            for field in ('exited', 'job_closed', 'stderr_drain_complete'):
                if getattr(cleanup, field, None) is not True:
                    raise ProviderSessionError('AGENT_NATIVE_CLEANUP_REQUIRED')
                evidence[field] = True
            return evidence

    def _require_open(self):
        if self._closing or self._closed:
            raise ProviderSessionError('AGENT_NATIVE_RUNTIME_DISABLED')
