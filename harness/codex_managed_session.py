"""Owned Codex app-server launcher with reviewed policy and explicit cleanup.

Launching successfully is not production admission or authentication evidence.
"""
from __future__ import annotations

from contextlib import ExitStack
import json
from pathlib import Path
import threading

from .codex_managed_client import ManagedCodexClient
from .codex_managed_profile import codex_profile_environment, lease_codex_profile
from .codex_session_client import CodexSessionClient
from .codex_session_transport import CodexSessionTransport
from .provider_session_contract import ProviderSessionError
from .provider_session_process import ProviderSessionProcessError, start_provider_session_process

_cleanup_holds: list[ManagedCodexSession] = []
_custody_lock = threading.RLock()


class ManagedCodexSession:
    admitted = False

    def __init__(self):
        self._lease = ExitStack()
        self.process = self.transport = self.client = self.raw_client = None
        self.config_digest = ''
        self.cleanup = None
        self.closed = False
        self._close_lock = threading.RLock()

    def close(self) -> bool:
        with self._close_lock:
            if self.closed:
                return True
            try:
                if self.process is not None:
                    self.cleanup = self.process.close()
                    if not (self.cleanup.exited and self.cleanup.job_closed
                            and self.cleanup.stderr_drain_complete):
                        return self._hold()
                if self.transport is not None and not self.transport.close(timeout=2):
                    return self._hold()
                if self.transport is None and self.process is not None:
                    self.process.stdin.close()
                    self.process.stdout.close()
                self._lease.close()
            except Exception:
                return self._hold()
            self.closed = True
            with _custody_lock:
                if self in _cleanup_holds:
                    _cleanup_holds.remove(self)
            return True

    def _hold(self) -> bool:
        # Retain policy/file custody when the process tree has not been proven
        # closed. The next launch is refused until explicit cleanup succeeds.
        with _custody_lock:
            if self not in _cleanup_holds:
                _cleanup_holds.append(self)
        return False


def retry_managed_codex_cleanup() -> bool:
    with _custody_lock:
        held = list(_cleanup_holds)
    for session in held:
        session.close()
    with _custody_lock:
        return not _cleanup_holds


def start_managed_codex_session(profile, *, executable: Path,
                                executable_sha256: str, model: str,
                                inventory=None) -> ManagedCodexSession:
    if (type(model) is not str or not model or len(model) > 256
            or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in model)):
        raise ProviderSessionError('MODEL_SELECTION_REQUIRED')
    with _custody_lock:
        if _cleanup_holds:
            raise ProviderSessionError('AGENT_NATIVE_CLEANUP_REQUIRED')
    session = ManagedCodexSession()
    try:
        before_resume = session._lease.enter_context(lease_codex_profile(profile, executable=executable,
            executable_sha256=executable_sha256, inventory=inventory))
        if not callable(before_resume):
            raise ProviderSessionError('AGENT_NATIVE_RUNTIME_DISABLED')
        session.process = start_provider_session_process(_argv(executable, model),
            cwd=profile.workspace, env=codex_profile_environment(profile),
            before_resume=before_resume)
        session.transport = CodexSessionTransport(session.process.stdin,
                                                 session.process.stdout, default_timeout=12)
        session.raw_client = CodexSessionClient(session.transport)
        session.raw_client.initialize(name='flywheel-managed-session')
        session.client = ManagedCodexClient(session.raw_client, workspace=profile.workspace,
                                            model=model)
        session.config_digest = session.client.config_digest
        return session
    except Exception as exc:
        if isinstance(exc, ProviderSessionProcessError):
            session.process = getattr(exc, 'owned_process', session.process)
        if not session.close():
            raise ProviderSessionError('AGENT_NATIVE_CLEANUP_REQUIRED') from None
        raise ProviderSessionError('AGENT_NATIVE_RUNTIME_DISABLED') from None


def _argv(executable: Path, model: str) -> list[str]:
    policy = {'model': model, 'model_provider': 'openai',
              'approval_policy': 'on-request', 'approvals_reviewer': 'user',
              'sandbox_mode': 'read-only', 'web_search': 'disabled',
              'features.hooks': False, 'features.apps': False, 'features.plugins': False,
              'mcp_servers': {}, 'notify': [], 'project_doc_max_bytes': 0}
    argv = [str(executable), 'app-server', '--stdio']
    for key, value in policy.items():
        argv.extend(['-c', key + '=' + ('{}' if value == {} else json.dumps(value))])
    return argv
