from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from harness.codex_managed_composition import (
    build_managed_codex_components,
    managed_codex_server_config,
)
from harness.codex_managed_inventory_lifecycle import (
    CodexManagedInventoryLifecycle,
    CodexManagedInventoryLifecycleError,
)
from harness.codex_session_types import CodexNotification


OWNER = "owner_" + "a" * 32
VERSION = "0.144.6"
MODEL = "gpt-5.6-sol"


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


class _LoginTransport:
    def __init__(self, session, *, success: bool = True):
        self.session = session
        self.success = success
        self.closed = False
        self._popped = False

    def request(self, method, params=None):
        if method == "account/login/start":
            return {
                "type": "chatgpt",
                "loginId": self.session.login_id,
                "authUrl": f"https://auth.openai.com/login/{self.session.login_id}",
            }
        if method == "account/read":
            return {"account": None, "requiresOpenaiAuth": True}
        if method == "model/list":
            return {"models": []}
        if method == "modelProvider/capabilities/read":
            return {"namespaceTools": False, "imageGeneration": False, "webSearch": False}
        raise AssertionError(method)

    def pop_notification(self, *, timeout=0.0):
        if self._popped or self.session.inventory is None:
            return None
        self._popped = True
        (self.session.profile.home / "auth.json").write_text(
            '{"synthetic":"metadata-only"}', encoding="utf-8")
        return CodexNotification(1, "account/login/completed", {
            "loginId": self.session.login_id,
            "success": self.success,
            "error": "" if self.success else "denied",
        })

    def notification_overflowed(self):
        return False


class _ManagedAuthSession:
    def __init__(self, profile, inventory, *, success: bool = True):
        self.profile = profile
        self.inventory = inventory
        self.login_id = "login-1"
        self.transport = _LoginTransport(self, success=success)
        self.client = SimpleNamespace(check_configuration=lambda: None)
        self.cleanup = None
        self.closed = False

    def close(self):
        self.cleanup = SimpleNamespace(exited=True, job_closed=True, stderr_drain_complete=True)
        self.transport.closed = True
        self.closed = True
        return True


class _ManagedAuthStarter:
    def __init__(self, *, success: bool = True):
        self.success = success
        self.calls = []
        self.sessions = []

    def __call__(self, profile, *, executable, executable_sha256, model, inventory=None):
        self.calls.append({"profile": profile, "inventory": inventory, "model": model})
        if inventory is None:
            _generated_home(profile)
        session = _ManagedAuthSession(profile, inventory, success=self.success)
        self.sessions.append(session)
        return session


def _exe(tmp_path):
    path = tmp_path / "codex.exe"
    path.write_bytes(b"synthetic managed codex executable")
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def _roots(tmp_path):
    roots = {
        "state": tmp_path / "state",
        "policy": tmp_path / "policy",
        "workspace": tmp_path / "workspace",
        "run": tmp_path / "run",
    }
    for path in roots.values():
        path.mkdir()
    executable, digest = _exe(tmp_path)
    roots.update({"executable": executable, "digest": digest})
    return roots


def _lifecycle(roots, starter):
    return CodexManagedInventoryLifecycle(
        state_root=roots["state"],
        policy_root=roots["policy"],
        workspace=roots["workspace"],
        executable=roots["executable"],
        executable_sha256=roots["digest"],
        configured_version=VERSION,
        version_provenance="synthetic-test",
        model=MODEL,
        start_session=starter,
    )


def _components(roots, lifecycle):
    config = managed_codex_server_config(
        executable=roots["executable"],
        executable_sha256=roots["digest"],
        model=MODEL,
        codex_version=VERSION,
        version_provenance="synthetic-test",
        policy_root=roots["policy"],
    )
    return build_managed_codex_components(
        repo_root=roots["workspace"],
        run_root=roots["run"],
        state_root=roots["state"],
        clock=lambda: "2026-09-16T00:00:00Z",
        config=config,
        lifecycle=lifecycle,
    )


def _guard_auth_content_reads(monkeypatch):
    original_open = Path.open

    def guarded_open(path, *args, **kwargs):
        mode = args[0] if args else kwargs.get("mode", "r")
        if Path(path).name == "auth.json" and "r" in mode:
            raise AssertionError("auth.json content was read")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded_open)


def test_managed_login_flow_records_auth_inventory_and_fresh_lifecycle_selects_it(
        tmp_path, monkeypatch):
    roots = _roots(tmp_path)
    starter = _ManagedAuthStarter()
    lifecycle = _lifecycle(roots, starter)
    components = _components(roots, lifecycle)
    monkeypatch.setattr(
        "harness.codex_app_server_client.CodexAppServerClient.connect",
        lambda **_: (_ for _ in ()).throw(AssertionError("ambient connect used")),
    )
    _guard_auth_content_reads(monkeypatch)

    started, start_status = components.codex_account_manager.start_login(
        OWNER, "browser", visible_ui_action=True)
    completed, completed_status = components.codex_account_manager.login_result(
        OWNER, started["login_id"])

    assert start_status == 202
    assert started["state"] == "login_started"
    assert completed_status == 200
    assert completed["state"] == "authenticated"
    assert completed["restart_persistence"] == "auth_extension_recorded"
    base_ref = starter.calls[1]["inventory"]
    assert [call["inventory"] for call in starter.calls] == [None, base_ref]
    assert base_ref is not None
    assert base_ref.sha256 != completed["inventory_sha256"]
    assert starter.sessions[0].closed is True
    assert starter.sessions[1].closed is True

    fresh_starter = _ManagedAuthStarter()
    fresh = _lifecycle(roots, fresh_starter)
    binding = fresh.account_client_for_owner(owner_ref=OWNER)

    assert binding.inventory.sha256 == completed["inventory_sha256"]
    assert fresh_starter.calls == [{
        "profile": binding.profile,
        "inventory": binding.inventory,
        "model": MODEL,
    }]
    assert components.shutdown() is True
    assert fresh.shutdown() is True


def test_unsuccessful_login_completion_does_not_persist_authenticated_inventory(tmp_path):
    roots = _roots(tmp_path)
    starter = _ManagedAuthStarter(success=False)
    lifecycle = _lifecycle(roots, starter)
    components = _components(roots, lifecycle)

    started, start_status = components.codex_account_manager.start_login(
        OWNER, "browser", visible_ui_action=True)
    completed, completed_status = components.codex_account_manager.login_result(
        OWNER, started["login_id"])

    assert start_status == 202
    assert completed_status == 200
    assert completed["state"] == "failed"
    assert "inventory_sha256" not in completed

    fresh = _lifecycle(roots, _ManagedAuthStarter())
    with pytest.raises(CodexManagedInventoryLifecycleError) as held:
        fresh.account_client_for_owner(owner_ref=OWNER)
    assert held.value.code == "BASELINE_ACCEPTED_INVENTORY_REQUIRED"
    assert components.shutdown() is True
    assert fresh.shutdown() is True
