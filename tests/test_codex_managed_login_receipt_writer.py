import hashlib
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from harness import codex_managed_profile_manifest as manifest
from harness.codex_account_binding import LoginCompletionContext, ManagedCodexAccountBinding
from harness.codex_account_route import codex_account_get, codex_account_post
from harness.codex_account_sessions import CodexAccountSessionManager
from harness.codex_managed_account_client import ManagedCodexAccountClient
from harness.codex_managed_profile import prepare_codex_profile
from harness.codex_managed_profile_auth_receipt import (
    MAX_AUTH_METADATA,
    CodexProfileLoginReceiptRef,
    read_login_receipt,
)
from harness.codex_session_types import CodexNotification


VERSION = "0.144.6"


class LoginTransport:
    def __init__(self, login_id="login-1"):
        self.login_id = login_id
        self.calls = []
        self.closed = False
        self.notifications = [CodexNotification(
            1, "account/login/completed", {"loginId": login_id, "success": True})]

    def request(self, method, params=None):
        self.calls.append((method, params))
        if method == "account/login/start":
            return {
                "type": "chatgpt",
                "loginId": self.login_id,
                "authUrl": f"https://auth.openai.com/login/{self.login_id}",
            }
        if method == "account/read":
            return {"account": None, "requiresOpenaiAuth": True}
        if method == "model/list":
            return {"models": []}
        if method == "modelProvider/capabilities/read":
            return {"namespaceTools": False, "imageGeneration": False, "webSearch": False}
        raise AssertionError(method)

    def pop_notification(self, *, timeout=0.0):
        return self.notifications.pop(0) if self.notifications else None

    def notification_overflowed(self):
        return False


class FakeManagedSession:
    def __init__(self, login_id="login-1", *, cleanup=True):
        self.transport = LoginTransport(login_id)
        self.client = SimpleNamespace(check_configuration=lambda: None)
        self.cleanup = None
        self.closed = False
        self._cleanup = cleanup

    def close(self):
        self.cleanup = SimpleNamespace(
            exited=self._cleanup,
            job_closed=self._cleanup,
            stderr_drain_complete=self._cleanup,
        )
        self.transport.closed = self._cleanup
        self.closed = self._cleanup
        return self._cleanup


def _exe(tmp_path):
    path = tmp_path / "codex.exe"
    path.write_bytes(b"fake codex executable")
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def _generated_home(profile):
    for name in (".personality_migration", "installation_id"):
        (profile.home / name).write_text("ok", encoding="utf-8")
    for name in (
            "goals_1.sqlite", "goals_1.sqlite-shm", "goals_1.sqlite-wal",
            "logs_2.sqlite", "logs_2.sqlite-shm", "logs_2.sqlite-wal",
            "memories_1.sqlite", "memories_1.sqlite-shm", "memories_1.sqlite-wal",
            "state_5.sqlite", "state_5.sqlite-shm", "state_5.sqlite-wal"):
        (profile.home / name).write_bytes(b"")
    (profile.home / "tmp").mkdir()
    system = profile.home / "skills" / ".system" / "openai-docs"
    system.mkdir(parents=True)
    (profile.home / "skills" / ".system" / ".codex-system-skills.marker").write_text(
        "system", encoding="utf-8")
    (system / "SKILL.md").write_text("builtin skill", encoding="utf-8")


def _fixture(tmp_path):
    state, workspace, policy = tmp_path / "state", tmp_path / "workspace", tmp_path / "policy"
    state.mkdir()
    workspace.mkdir()
    policy.mkdir()
    profile = prepare_codex_profile(state, workspace=workspace, owner_ref="owner-1")
    _generated_home(profile)
    executable, digest = _exe(tmp_path)
    inventory = manifest.capture_generated_profile_manifest(
        profile, executable=executable, executable_sha256=digest, codex_version=VERSION,
        bootstrap_receipt_sha256="d" * 64, policy_root=policy)
    return profile, policy, executable, digest, inventory


def _closed_binding(profile, policy, executable, digest, inventory, *, login_id="login-1"):
    session = FakeManagedSession(login_id)
    client = ManagedCodexAccountClient(session)
    client.close()
    binding = ManagedCodexAccountBinding(
        client=client,
        profile=profile,
        inventory=inventory,
        executable=executable,
        executable_sha256=digest,
        codex_version=VERSION,
        policy_root=policy,
    )
    return binding, session


def _ctx(binding, *, login_id="login-1", mode="browser", completed_login_id=None, success=True):
    return LoginCompletionContext(
        "owner-1",
        login_id,
        mode,
        {"loginId": completed_login_id or login_id, "success": success},
        binding,
    )


def _guard_auth_content_reads(monkeypatch):
    original_open = Path.open

    def guarded_open(path, *args, **kwargs):
        if Path(path).name == "auth.json":
            raise AssertionError("auth content was read")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded_open)


def test_receipt_writer_records_exact_auth_json_without_reading_auth_contents(tmp_path, monkeypatch):
    from harness.codex_managed_login_receipt_writer import (
        record_login_success,
        write_login_receipt,
    )

    profile, policy, executable, digest, inventory = _fixture(tmp_path)
    (profile.home / "auth.json").write_text("secret-token-material", encoding="utf-8")
    binding, _session = _closed_binding(profile, policy, executable, digest, inventory)
    ctx = _ctx(binding)
    _guard_auth_content_reads(monkeypatch)

    receipt_ref = write_login_receipt(ctx)
    assert isinstance(receipt_ref, CodexProfileLoginReceiptRef)
    receipt = read_login_receipt(receipt_ref)
    assert receipt["source_inventory_sha256"] == inventory.sha256
    assert receipt["codex"] == {"version": VERSION, "executable_sha256": digest}
    assert receipt["bindings"]["home_identity"] == profile.home_identity.to_json_dict()
    assert receipt["login"] == {
        "mode": "browser",
        "login_id_sha256": hashlib.sha256(b"login-1").hexdigest(),
    }
    assert receipt["completion"] == {"success": True}
    assert receipt["cleanup"]["exited"] is True
    assert receipt["auth_entries"] == [
        {"path": "auth.json", "kind": "file", "max_bytes": MAX_AUTH_METADATA}]

    extended = record_login_success(ctx)
    data = manifest.read_restart_manifest(extended)
    assert data["auth_extension"]["content_read"] is False
    assert data["auth_extension"]["exact_paths_only"] is True
    assert data["auth_extension"]["auth_paths"] == ["auth.json"]
    manifest.verify_restart_inventory(profile, extended,
        executable=executable, executable_sha256=digest)


def test_receipt_writer_rejects_missing_policy_inexact_completion_and_unclosed_client(tmp_path):
    from harness.codex_managed_login_receipt_writer import (
        CodexManagedLoginReceiptWriterError,
        write_login_receipt,
    )

    with pytest.raises(CodexManagedLoginReceiptWriterError) as wrong_context:
        write_login_receipt(object())
    assert wrong_context.value.code == "LOGIN_RECEIPT_WRONG_CONTEXT"

    profile, policy, executable, digest, inventory = _fixture(tmp_path)
    binding, _session = _closed_binding(profile, policy, executable, digest, inventory)
    with pytest.raises(CodexManagedLoginReceiptWriterError) as missing:
        write_login_receipt(_ctx(binding))
    assert missing.value.code == "LOGIN_RECEIPT_AUTH_POLICY_REQUIRED"

    (profile.home / "auth.json").write_text("secret", encoding="utf-8")
    with pytest.raises(CodexManagedLoginReceiptWriterError) as mismatch:
        write_login_receipt(_ctx(binding, completed_login_id="other-login"))
    assert mismatch.value.code == "LOGIN_RECEIPT_COMPLETION_MISMATCH"

    open_client = ManagedCodexAccountClient(FakeManagedSession())
    open_binding = ManagedCodexAccountBinding(
        client=open_client, profile=profile, inventory=inventory, executable=executable,
        executable_sha256=digest, codex_version=VERSION, policy_root=policy)
    with pytest.raises(CodexManagedLoginReceiptWriterError) as unclosed:
        write_login_receipt(_ctx(open_binding))
    assert unclosed.value.code == "LOGIN_RECEIPT_CLEANUP_REQUIRED"


def test_success_hook_holds_unlisted_auth_root_without_current_process_claim(tmp_path):
    from harness.codex_managed_login_receipt_writer import record_login_success

    profile, policy, executable, digest, inventory = _fixture(tmp_path)
    (profile.home / "auth.json").write_text("secret", encoding="utf-8")
    (profile.home / "auth2.json").write_text("surprise", encoding="utf-8")

    def factory(*, owner_ref):
        client = ManagedCodexAccountClient(FakeManagedSession())
        return ManagedCodexAccountBinding(
            client=client, profile=profile, inventory=inventory, executable=executable,
            executable_sha256=digest, codex_version=VERSION, policy_root=policy)

    manager = CodexAccountSessionManager(
        owner_client_factory=factory,
        login_success_hook=record_login_success,
    )
    assert codex_account_post("/api/codex/account/login/start", {"mode": "browser"},
        owner_ref="owner-1", manager=manager, visible_ui_action=True)[1] == 202
    body, status = codex_account_get("/api/codex/account/login/result",
        "login_id=login-1", owner_ref="owner-1", manager=manager)
    assert status == 200
    assert body["state"] == "authenticated_restart_held"
    assert "current_process_usable" not in body
    assert "restart_persistence" not in body


def test_receipt_writer_requires_regular_single_link_auth_json(tmp_path):
    from harness.codex_managed_login_receipt_writer import (
        CodexManagedLoginReceiptWriterError,
        write_login_receipt,
    )

    profile, policy, executable, digest, inventory = _fixture(tmp_path)
    (profile.home / "auth.json").mkdir()
    binding, _session = _closed_binding(profile, policy, executable, digest, inventory)
    with pytest.raises(CodexManagedLoginReceiptWriterError) as nonregular:
        write_login_receipt(_ctx(binding))
    assert nonregular.value.code == "LOGIN_RECEIPT_AUTH_PATH_UNSAFE"

    (profile.home / "auth.json").rmdir()
    (profile.home / "auth.json").write_text("secret", encoding="utf-8")
    try:
        os.link(profile.home / "auth.json", tmp_path / "auth-hardlink")
    except OSError:
        pytest.skip("hardlinks unavailable on this filesystem")
    with pytest.raises(CodexManagedLoginReceiptWriterError) as hardlink:
        write_login_receipt(_ctx(binding))
    assert hardlink.value.code == "LOGIN_RECEIPT_AUTH_PATH_UNSAFE"
