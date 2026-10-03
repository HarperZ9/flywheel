import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from harness.codex_account_binding import ManagedCodexAccountBinding
from harness.codex_managed_profile import prepare_codex_profile
from harness.codex_managed_profile_manifest import (
    CodexProfileInventoryRef,
    read_restart_manifest,
)


def _exe(tmp_path, name="codex.exe", body=b"synthetic codex"):
    path = tmp_path / name
    path.write_bytes(body)
    return path, hashlib.sha256(body).hexdigest()


def _lifecycle(tmp_path, starter, **overrides):
    from harness.codex_managed_inventory_lifecycle import CodexManagedInventoryLifecycle

    state, policy, workspace = tmp_path / "state", tmp_path / "policy", tmp_path / "workspace"
    for root in (state, policy, workspace):
        root.mkdir(exist_ok=True)
    executable, digest = overrides.pop("executable_pair", _exe(tmp_path))
    values = {
        "state_root": state,
        "policy_root": policy,
        "workspace": workspace,
        "executable": executable,
        "executable_sha256": digest,
        "configured_version": "0.144.6",
        "version_provenance": "test flag",
        "model": "gpt-5.6-sol",
        "start_session": starter,
    }
    values.update(overrides)
    return CodexManagedInventoryLifecycle(**values), policy


def _generated_home(profile):
    for name in (".personality_migration", "installation_id"):
        (profile.home / name).write_text("ok", encoding="utf-8")
    for name in (
            "goals_1.sqlite", "goals_1.sqlite-shm", "goals_1.sqlite-wal",
            "logs_2.sqlite", "logs_2.sqlite-shm", "logs_2.sqlite-wal",
            "memories_1.sqlite", "memories_1.sqlite-shm", "memories_1.sqlite-wal",
            "state_5.sqlite", "state_5.sqlite-shm", "state_5.sqlite-wal"):
        (profile.home / name).write_bytes(b"")
    system = profile.home / "skills" / ".system" / "openai-docs"
    system.mkdir(parents=True)
    (profile.home / "skills" / ".system" / ".codex-system-skills.marker").write_text(
        "system", encoding="utf-8")
    (system / "SKILL.md").write_text("builtin skill", encoding="utf-8")
    (profile.home / "tmp").mkdir()


class FakeSession:
    def __init__(self, *, close_ok=True):
        self.close_ok = close_ok
        self.closed = False
        self.cleanup = None
        self.transport = SimpleNamespace(
            calls=[],
            notifications=[],
            request=self._request,
            pop_notification=lambda timeout=0.0: None,
            notification_overflowed=lambda: False,
        )
        self.client = SimpleNamespace(check_configuration=lambda: None)

    def _request(self, method, params=None):
        self.transport.calls.append((method, params))
        return {"method": method}

    def close(self):
        self.cleanup = SimpleNamespace(
            exited=self.close_ok,
            job_closed=self.close_ok,
            stderr_drain_complete=self.close_ok,
        )
        self.closed = self.close_ok
        return self.close_ok


class Starter:
    def __init__(self, *, close_ok=True):
        self.close_ok = close_ok
        self.calls = []
        self.sessions = []

    def __call__(self, profile, *, executable, executable_sha256, model, inventory=None):
        self.calls.append({"profile": profile, "model": model, "inventory": inventory})
        if inventory is None:
            _generated_home(profile)
        session = FakeSession(close_ok=self.close_ok)
        self.sessions.append(session)
        return session


def _json_files(policy):
    return sorted(path for path in policy.rglob("*.json"))


def test_first_status_bootstrap_writes_no_auth_receipt_and_inventory_ref(tmp_path):
    starter = Starter()
    lifecycle, policy = _lifecycle(tmp_path, starter)

    ref = lifecycle.ensure_baseline_inventory("owner-1")

    assert isinstance(ref, CodexProfileInventoryRef)
    assert len(starter.calls) == 1
    assert starter.calls[0]["inventory"] is None
    receipt_paths = [path for path in _json_files(policy) if "bootstrap-receipt" in path.name]
    assert len(receipt_paths) == 1
    receipt = json.loads(receipt_paths[0].read_text(encoding="utf-8"))
    assert receipt["schema"] == "flywheel.codex-managed-no-auth-bootstrap-receipt/v1"
    assert receipt["auth"]["content_read"] is False
    assert receipt["cleanup"] == {
        "process_exited": True,
        "job_closed": True,
        "stderr_drain_complete": True,
    }
    assert receipt["binding"]["codex"] == {
        "configured_version": "0.144.6",
        "version_provenance": "test flag",
        "model": "gpt-5.6-sol",
    }
    manifest = read_restart_manifest(ref)
    assert manifest["bootstrap"]["receipt_sha256"] == hashlib.sha256(
        receipt_paths[0].read_bytes()).hexdigest()


def test_second_account_client_uses_accepted_inventory_for_generated_profile(tmp_path):
    starter = Starter()
    lifecycle, _policy = _lifecycle(tmp_path, starter)
    ref = lifecycle.ensure_baseline_inventory("owner-1")
    starter.calls.clear()

    binding = lifecycle.account_client_for_owner(owner_ref="owner-1")

    assert isinstance(binding, ManagedCodexAccountBinding)
    assert binding.inventory == ref
    assert binding.codex_version == "0.144.6"
    assert starter.calls == [{"profile": binding.profile, "model": "gpt-5.6-sol", "inventory": ref}]
    assert binding.client.get_account(refresh_token=False) == {"method": "account/read"}
    assert lifecycle.shutdown() is True


def test_generated_profile_without_accepted_inventory_fails_closed(tmp_path):
    starter = Starter()
    lifecycle, _policy = _lifecycle(tmp_path, starter)
    profile = prepare_codex_profile(tmp_path / "state", workspace=tmp_path / "workspace",
                                    owner_ref="owner-1")
    _generated_home(profile)

    with pytest.raises(RuntimeError, match="BASELINE_ACCEPTED_INVENTORY_REQUIRED"):
        lifecycle.ensure_baseline_inventory("owner-1")

    assert starter.calls == []


def test_cleanup_failure_blocks_inventory_write_and_can_be_retried(tmp_path):
    starter = Starter(close_ok=False)
    lifecycle, policy = _lifecycle(tmp_path, starter)

    with pytest.raises(RuntimeError, match="BASELINE_CLEANUP_REQUIRED"):
        lifecycle.ensure_baseline_inventory("owner-1")

    assert _json_files(policy) == []
    assert lifecycle.shutdown() is False
    starter.sessions[0].close_ok = True
    assert lifecycle.shutdown() is True


@pytest.mark.parametrize("field", ["model", "configured_version", "executable"])
def test_binding_drift_does_not_reuse_or_replace_existing_baseline(tmp_path, field):
    starter = Starter()
    lifecycle, _policy = _lifecycle(tmp_path, starter)
    lifecycle.ensure_baseline_inventory("owner-1")
    drift_starter = Starter()
    kwargs = {}
    if field == "model":
        kwargs["model"] = "gpt-6-astra"
    elif field == "configured_version":
        kwargs["configured_version"] = "0.145.0"
    else:
        kwargs["executable_pair"] = _exe(tmp_path, "other-codex.exe", b"other")
    drifted, _ = _lifecycle(tmp_path, drift_starter, **kwargs)

    with pytest.raises(RuntimeError, match="BASELINE_ACCEPTED_INVENTORY_REQUIRED"):
        drifted.ensure_baseline_inventory("owner-1")

    assert drift_starter.calls == []


def test_verified_inventory_acceptance_rejects_unsafe_ref_path(tmp_path):
    starter = Starter()
    lifecycle, _policy = _lifecycle(tmp_path, starter)
    ref = lifecycle.ensure_baseline_inventory("owner-1")

    assert lifecycle.accept_verified_inventory("owner-1", ref) == ref
    forged = CodexProfileInventoryRef(tmp_path / "outside.json", "0" * 64)
    with pytest.raises(RuntimeError, match="BASELINE_INVENTORY_REJECTED"):
        lifecycle.accept_verified_inventory("owner-1", forged)
