from pathlib import Path

from codex_account_fakes import FakeClient, browser_login

from harness.codex_account_binding import ManagedCodexAccountBinding
from harness.codex_account_route import codex_account_get, codex_account_post
from harness.codex_account_sessions import CodexAccountSessionManager
from harness.codex_managed_profile_manifest import CodexProfileInventoryRef, CodexProfileManifestError


class ProofClient(FakeClient):
    def close(self):
        self.closed = True
        return True


def _completed(login_id='login-1', success=True):
    return {'method': 'account/login/completed',
            'params': {'loginId': login_id, 'success': success}}


def _binding(client):
    return ManagedCodexAccountBinding(client=client, profile=object(), inventory=object(),
        executable=Path('/codex.exe'), executable_sha256='a' * 64,
        codex_version='0.144.6', policy_root=Path('/policy'))


def _inventory():
    return CodexProfileInventoryRef(path=Path('/policy/restart-manifest.json'), sha256='b' * 64)


def _start(manager):
    return codex_account_post('/api/codex/account/login/start', {'mode': 'browser'},
        owner_ref='owner-a', manager=manager, visible_ui_action=True)


def test_login_success_hook_receives_binding_after_cleanup():
    client = ProofClient(login=browser_login('login-1'), notifications=[_completed()])
    seen = []

    def hook(ctx):
        assert client.closed is True
        seen.append((ctx.owner_ref, ctx.login_id, ctx.mode, ctx.binding.client))
        return _inventory()

    manager = CodexAccountSessionManager(
        client_factory=lambda: _binding(client), login_success_hook=hook)
    assert _start(manager)[1] == 202
    body, status = codex_account_get('/api/codex/account/login/result',
        'login_id=login-1', owner_ref='owner-a', manager=manager)
    assert status == 200
    assert body['state'] == 'authenticated'
    assert body['restart_persistence'] == 'auth_extension_recorded'
    assert body['inventory_sha256'] == 'b' * 64
    assert seen == [('owner-a', 'login-1', 'browser', client)]


def test_login_hook_is_not_called_without_successful_completion():
    calls = []
    client = ProofClient(login=browser_login('login-1'), notifications=[_completed(success=False)])
    manager = CodexAccountSessionManager(
        client_factory=lambda: _binding(client), login_success_hook=lambda ctx: calls.append(ctx))
    assert _start(manager)[1] == 202
    body, status = codex_account_get('/api/codex/account/login/result',
        'login_id=login-1', owner_ref='owner-a', manager=manager)
    assert status == 200
    assert body['state'] == 'failed'
    assert calls == []


def test_owner_factory_binding_feeds_success_hook_without_ambient_fallback(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('ambient client factory must not run')

    monkeypatch.setattr('harness.codex_account_sessions.CodexAppServerClient.connect', forbidden)
    seen = []

    def factory(*, owner_ref):
        client = ProofClient(login=browser_login('login-owner'),
                             notifications=[_completed('login-owner')])
        binding = _binding(client)
        return ManagedCodexAccountBinding(
            client=binding.client, profile=owner_ref, inventory=binding.inventory,
            executable=binding.executable, executable_sha256=binding.executable_sha256,
            codex_version=binding.codex_version, policy_root=binding.policy_root)

    def hook(ctx):
        seen.append((ctx.owner_ref, ctx.binding.profile, ctx.binding.client.closed))
        return _inventory()

    manager = CodexAccountSessionManager(owner_client_factory=factory, login_success_hook=hook)
    assert _start(manager)[1] == 202
    body, status = codex_account_get('/api/codex/account/login/result',
        'login_id=login-owner', owner_ref='owner-a', manager=manager)
    assert status == 200
    assert body['state'] == 'authenticated'
    assert seen == [('owner-a', 'owner-a', True)]


def test_login_hook_failure_or_cleanup_failure_holds_restart_without_secret_leak():
    client = ProofClient(login=browser_login('login-1'), notifications=[_completed()])

    def bad_hook(_ctx):
        raise RuntimeError('bad sk-SECRET')

    manager = CodexAccountSessionManager(client_factory=lambda: _binding(client),
                                        login_success_hook=bad_hook)
    assert _start(manager)[1] == 202
    body, status = codex_account_get('/api/codex/account/login/result',
        'login_id=login-1', owner_ref='owner-a', manager=manager)
    assert status == 200
    assert body['state'] == 'authenticated_restart_held'
    assert 'SECRET' not in repr(body)


def test_login_hook_failure_reports_typed_error_code_without_secret_leak():
    client = ProofClient(login=browser_login('login-coded'),
                         notifications=[_completed('login-coded')])

    def bad_hook(_ctx):
        raise CodexProfileManifestError('MANIFEST_TREE_MISMATCH')

    manager = CodexAccountSessionManager(client_factory=lambda: _binding(client),
                                        login_success_hook=bad_hook)
    assert _start(manager)[1] == 202
    body, status = codex_account_get('/api/codex/account/login/result',
        'login_id=login-coded', owner_ref='owner-a', manager=manager)
    assert status == 200
    assert body['state'] == 'authenticated_restart_held'
    assert body['reason'] == 'MANIFEST_TREE_MISMATCH'
    assert 'SECRET' not in repr(body)


def test_login_hook_failure_rejects_foreign_error_codes_without_secret_leak():
    class ForeignCodeError(RuntimeError):
        pass

    for index, code in enumerate((
            'password=hunter2',
            'C:/Users/example/.codex/auth.json',
            'MANIFEST_TREE_MISMATCH',
    )):
        login = f'login-foreign-{index}'
        client = ProofClient(login=browser_login(login),
                             notifications=[_completed(login)])

        def bad_hook(_ctx, value=code):
            exc = ForeignCodeError('bad sk-SECRET')
            exc.code = value
            raise exc

        manager = CodexAccountSessionManager(client_factory=lambda: _binding(client),
                                            login_success_hook=bad_hook)
        assert _start(manager)[1] == 202
        body, status = codex_account_get('/api/codex/account/login/result',
            f'login_id={login}', owner_ref='owner-a', manager=manager)
        assert status == 200
        assert body['state'] == 'authenticated_restart_held'
        assert body['reason'] == 'ForeignCodeError'
        serialized = repr(body)
        assert 'hunter2' not in serialized
        assert 'auth.json' not in serialized
        assert 'SECRET' not in serialized


def test_login_hook_failure_rejects_unknown_internal_manifest_code():
    client = ProofClient(login=browser_login('login-unknown-code'),
                         notifications=[_completed('login-unknown-code')])

    def bad_hook(_ctx):
        raise CodexProfileManifestError('MANIFEST_FUTURE_UNKNOWN')

    manager = CodexAccountSessionManager(client_factory=lambda: _binding(client),
                                        login_success_hook=bad_hook)
    assert _start(manager)[1] == 202
    body, status = codex_account_get('/api/codex/account/login/result',
        'login_id=login-unknown-code', owner_ref='owner-a', manager=manager)
    assert status == 200
    assert body['state'] == 'authenticated_restart_held'
    assert body['reason'] == 'CodexProfileManifestError'
    assert 'MANIFEST_FUTURE_UNKNOWN' not in repr(body)


def test_invalid_receipt_and_cleanup_failures_hold_restart_without_secret_leak():
    wrong = ProofClient(login=browser_login('login-bad-ref'),
                        notifications=[_completed('login-bad-ref')])
    manager = CodexAccountSessionManager(client_factory=lambda: _binding(wrong),
                                        login_success_hook=lambda ctx: object())
    assert _start(manager)[1] == 202
    body, status = codex_account_get('/api/codex/account/login/result',
        'login_id=login-bad-ref', owner_ref='owner-a', manager=manager)
    assert status == 200
    assert body['state'] == 'authenticated_restart_held'

    class NoClose:
        def __init__(self):
            self.login = browser_login('login-noclose')
            self.notifications = [_completed('login-noclose')]

        def start_chatgpt_login(self):
            return self.login

        def pop_notification(self, **_kwargs):
            return self.notifications.pop(0) if self.notifications else None

        def notification_overflowed(self):
            return False

    calls = []
    manager = CodexAccountSessionManager(client_factory=lambda: _binding(NoClose()),
                                        login_success_hook=lambda ctx: calls.append(ctx) or _inventory())
    assert _start(manager)[1] == 202
    body, status = codex_account_get('/api/codex/account/login/result',
        'login_id=login-noclose', owner_ref='owner-a', manager=manager)
    assert status == 200
    assert body['state'] == 'authenticated_restart_held'
    assert calls == []

    no_proof = FakeClient(login=browser_login('login-no-proof'),
                          notifications=[_completed('login-no-proof')])
    calls = []
    manager = CodexAccountSessionManager(client_factory=lambda: _binding(no_proof),
                                        login_success_hook=lambda ctx: calls.append(ctx) or _inventory())
    assert _start(manager)[1] == 202
    body, status = codex_account_get('/api/codex/account/login/result',
        'login_id=login-no-proof', owner_ref='owner-a', manager=manager)
    assert status == 200
    assert body['state'] == 'authenticated_restart_held'
    assert calls == []

    class CleanupFails(FakeClient):
        def close(self):
            self.closed = True
            raise RuntimeError('cleanup sk-SECRET')

    held = CleanupFails(login=browser_login('login-2'), notifications=[_completed('login-2')])
    manager = CodexAccountSessionManager(client_factory=lambda: _binding(held),
                                        login_success_hook=lambda ctx: _inventory())
    assert _start(manager)[1] == 202
    body, status = codex_account_get('/api/codex/account/login/result',
        'login_id=login-2', owner_ref='owner-a', manager=manager)
    assert status == 200
    assert body['state'] == 'authenticated_restart_held'
    assert 'SECRET' not in repr(body)
