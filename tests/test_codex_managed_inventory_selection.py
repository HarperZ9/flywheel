import hashlib
from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest

from harness.codex_managed_profile import prepare_codex_profile
from harness.codex_managed_profile_auth_extension import extend_manifest_after_explicit_login
from harness.codex_managed_profile_auth_receipt import CodexProfileLoginReceiptRef, LOGIN_RECEIPT_SCHEMA
from harness.codex_managed_profile_manifest import CodexProfileInventoryRef
from harness.evidence_json import canonical_bytes
from harness.private_artifact_fs import open_artifact_root


def _exe(tmp_path):
    path = tmp_path / "codex.exe"
    path.write_bytes(b"synthetic codex")
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
    system = profile.home / "skills" / ".system" / "openai-docs"
    system.mkdir(parents=True)
    (profile.home / "skills" / ".system" / ".codex-system-skills.marker").write_text(
        "system", encoding="utf-8")
    (system / "SKILL.md").write_text("builtin skill", encoding="utf-8")
    (profile.home / "tmp").mkdir()


def _write_arg0_tree(profile, executable, suffix):
    tmp = profile.home / "tmp"
    if tmp.exists():
        shutil.rmtree(tmp)
    leaf = tmp / "arg0" / f"codex-arg0{suffix}"
    leaf.mkdir(parents=True)
    (leaf / ".lock").write_bytes(b"")
    body = f'@echo off\n"{executable}" --codex-run-as-apply-patch %*\n'.encode()
    (leaf / "apply_patch.bat").write_bytes(body)
    (leaf / "applypatch.bat").write_bytes(body)


class FakeSession:
    def __init__(self):
        self.cleanup = None
        self.transport = SimpleNamespace(
            request=lambda method, params=None: {"method": method},
            pop_notification=lambda timeout=0.0: None,
            notification_overflowed=lambda: False,
        )
        self.client = SimpleNamespace(check_configuration=lambda: None)

    def close(self):
        self.cleanup = SimpleNamespace(exited=True, job_closed=True, stderr_drain_complete=True)
        return True


class Starter:
    def __init__(self):
        self.calls = []

    def __call__(self, profile, *, executable, executable_sha256, model, inventory=None):
        self.calls.append(inventory)
        if inventory is None:
            _generated_home(profile)
        return FakeSession()


class RuntimeMutatingStarter(Starter):
    def __init__(self, executable):
        super().__init__()
        self.executable = executable
        self.runtime_starts = 0

    def __call__(self, profile, *, executable, executable_sha256, model, inventory=None):
        session = super().__call__(profile, executable=executable,
                                   executable_sha256=executable_sha256,
                                   model=model, inventory=inventory)
        if inventory is not None:
            self.runtime_starts += 1
            (profile.home / "models_cache.json").write_text("x" * 8192, encoding="utf-8")
            _write_arg0_tree(profile, self.executable, f"ROT{self.runtime_starts:03d}")
        return session


def _lifecycle(tmp_path, starter, *, state=None, policy=None, workspace=None, exe_pair=None):
    from harness.codex_managed_inventory_lifecycle import CodexManagedInventoryLifecycle

    state = state or tmp_path / "state"
    policy = policy or tmp_path / "policy"
    workspace = workspace or tmp_path / "workspace"
    for root in (state, policy, workspace):
        root.mkdir(exist_ok=True)
    executable, executable_sha = exe_pair or _exe(tmp_path)
    return CodexManagedInventoryLifecycle(
        state_root=state,
        policy_root=policy,
        workspace=workspace,
        executable=executable,
        executable_sha256=executable_sha,
        configured_version="0.144.6",
        version_provenance="test",
        model="gpt-5.6-sol",
        start_session=starter,
    ), (state, policy, workspace, executable, executable_sha)


def _login_receipt(policy, profile, source_ref, executable_sha, *, login_id="login-1"):
    receipt = {
        "schema": LOGIN_RECEIPT_SCHEMA,
        "source_inventory_sha256": source_ref.sha256,
        "codex": {"version": "0.144.6", "executable_sha256": executable_sha},
        "bindings": {
            "home_identity": profile.home_identity.to_json_dict(),
            "workspace_identity": profile.workspace_identity.to_json_dict(),
        },
        "login": {
            "mode": "login_with_chatgpt",
            "login_id_sha256": hashlib.sha256(login_id.encode("utf-8")).hexdigest(),
        },
        "completion": {"success": True},
        "cleanup": {"exited": True, "job_closed": True, "stderr_drain_complete": True},
        "auth_entries": [{"path": "auth.json", "kind": "file", "max_bytes": 16 * 1024 * 1024}],
    }
    raw = canonical_bytes(receipt)
    digest = hashlib.sha256(raw).hexdigest()
    rel = f"codex-policy/{source_ref.sha256}/login-receipts/{digest}.json"
    with open_artifact_root(policy) as root:
        root.write_new_or_same(rel, raw)
    return CodexProfileLoginReceiptRef(path=policy / rel, sha256=digest), login_id


def _auth_inventory(policy, profile, base_ref, executable, executable_sha, *, login_id="login-1"):
    receipt, login_id = _login_receipt(policy, profile, base_ref, executable_sha, login_id=login_id)
    return extend_manifest_after_explicit_login(
        profile,
        base_ref,
        executable=executable,
        executable_sha256=executable_sha,
        codex_version="0.144.6",
        login_receipt=receipt,
        policy_root=policy,
        expected_login_id=login_id,
        expected_mode="login_with_chatgpt",
    )


def _binding_dir(policy):
    return next(policy.rglob("baseline-inventory-ref.json")).parent


def test_auth_extended_inventory_is_current_for_same_and_fresh_lifecycle(tmp_path, monkeypatch):
    starter = Starter()
    lifecycle, roots = _lifecycle(tmp_path, starter)
    state, policy, workspace, executable, executable_sha = roots
    base_ref = lifecycle.ensure_baseline_inventory("owner-1")
    profile = prepare_codex_profile(state, workspace=workspace, owner_ref="owner-1")
    (profile.home / "auth.json").write_text('{"token":"metadata-not-read"}', encoding="utf-8")
    auth_ref = _auth_inventory(policy, profile, base_ref, executable, executable_sha)
    original_open = Path.open

    def guarded_open(path, *args, **kwargs):
        if Path(path).name == "auth.json":
            raise AssertionError("auth contents were read")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded_open)
    assert lifecycle.accept_verified_inventory("owner-1", auth_ref) == auth_ref
    starter.calls.clear()
    assert lifecycle.account_client_for_owner(owner_ref="owner-1").inventory == auth_ref
    assert starter.calls == [auth_ref]
    assert lifecycle.shutdown() is True

    fresh_starter = Starter()
    fresh, _ = _lifecycle(
        tmp_path,
        fresh_starter,
        state=state,
        policy=policy,
        workspace=workspace,
        exe_pair=(executable, executable_sha),
    )
    assert fresh.account_client_for_owner(owner_ref="owner-1").inventory == auth_ref
    assert fresh_starter.calls == [auth_ref]
    assert fresh.shutdown() is True


def test_auth_inventory_survives_runtime_model_cache_and_arg0_rotation(tmp_path):
    setup_starter = Starter()
    lifecycle, roots = _lifecycle(tmp_path, setup_starter)
    state, policy, workspace, executable, executable_sha = roots
    base_ref = lifecycle.ensure_baseline_inventory("owner-1")
    profile = prepare_codex_profile(state, workspace=workspace, owner_ref="owner-1")
    (profile.home / "auth.json").write_text("secret", encoding="utf-8")
    _write_arg0_tree(profile, executable, "LOGIN1")
    auth_ref = _auth_inventory(policy, profile, base_ref, executable, executable_sha)
    assert lifecycle.accept_verified_inventory("owner-1", auth_ref) == auth_ref

    starter = RuntimeMutatingStarter(executable)
    runtime, _ = _lifecycle(tmp_path, starter, state=state, policy=policy,
                            workspace=workspace, exe_pair=(executable, executable_sha))
    first, *_ = runtime.runtime_session_for_owner(owner_ref="owner-1")
    first.close()
    second, _profile, inventory, _manifest = runtime.runtime_session_for_owner(
        owner_ref="owner-1")

    assert inventory == auth_ref
    assert [call.sha256 if call is not None else None for call in starter.calls] == [
        auth_ref.sha256, auth_ref.sha256]
    second.close()
    assert runtime.shutdown() is True


def test_invalid_stale_inventory_update_is_rejected_after_auth_file(tmp_path):
    starter = Starter()
    lifecycle, roots = _lifecycle(tmp_path, starter)
    state, policy, workspace, executable, executable_sha = roots
    base_ref = lifecycle.ensure_baseline_inventory("owner-1")
    profile = prepare_codex_profile(state, workspace=workspace, owner_ref="owner-1")
    (profile.home / "auth.json").write_text("secret", encoding="utf-8")
    auth_ref = _auth_inventory(policy, profile, base_ref, executable, executable_sha)

    with pytest.raises(RuntimeError, match="BASELINE_INVENTORY_REJECTED"):
        lifecycle.accept_verified_inventory("owner-1", base_ref)

    assert lifecycle.accept_verified_inventory("owner-1", auth_ref) == auth_ref


def test_tampered_accepted_record_fails_closed(tmp_path):
    starter = Starter()
    lifecycle, roots = _lifecycle(tmp_path, starter)
    state, policy, workspace, executable, executable_sha = roots
    base_ref = lifecycle.ensure_baseline_inventory("owner-1")
    profile = prepare_codex_profile(state, workspace=workspace, owner_ref="owner-1")
    (profile.home / "auth.json").write_text("secret", encoding="utf-8")
    auth_ref = _auth_inventory(policy, profile, base_ref, executable, executable_sha)
    lifecycle.accept_verified_inventory("owner-1", auth_ref)
    tampered = canonical_bytes({
        "schema": "flywheel.codex-managed-baseline-inventory-ref/v1",
        "binding_sha256": "0" * 64,
        "binding": {},
        "inventory": {"path": "codex-policy/bad/restart-manifest.json", "sha256": "1" * 64},
    })
    ( _binding_dir(policy) / "accepted-inventories" / ("f" * 64 + ".json") ).write_bytes(tampered)

    with pytest.raises(RuntimeError, match="BASELINE_INVENTORY_REJECTED"):
        lifecycle.account_client_for_owner(owner_ref="owner-1")


def test_second_matching_auth_update_is_rejected_as_ambiguous(tmp_path):
    starter = Starter()
    lifecycle, roots = _lifecycle(tmp_path, starter)
    state, policy, workspace, executable, executable_sha = roots
    base_ref = lifecycle.ensure_baseline_inventory("owner-1")
    profile = prepare_codex_profile(state, workspace=workspace, owner_ref="owner-1")
    (profile.home / "auth.json").write_text("secret", encoding="utf-8")
    first = _auth_inventory(policy, profile, base_ref, executable, executable_sha, login_id="login-1")
    second = _auth_inventory(policy, profile, base_ref, executable, executable_sha, login_id="login-2")
    assert first.sha256 != second.sha256
    assert lifecycle.accept_verified_inventory("owner-1", first) == first

    with pytest.raises(RuntimeError, match="BASELINE_INVENTORY_AMBIGUOUS"):
        lifecycle.accept_verified_inventory("owner-1", second)

    assert lifecycle.account_client_for_owner(owner_ref="owner-1").inventory == first
    assert lifecycle.shutdown() is True
