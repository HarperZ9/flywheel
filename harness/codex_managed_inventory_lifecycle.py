"""No-auth Codex baseline inventory lifecycle."""
from __future__ import annotations

import hashlib
from pathlib import Path
import re
import threading
from typing import Any

from .codex_account_binding import ManagedCodexAccountBinding
from .codex_account_safety import owner_ref as safe_owner_ref
from .codex_managed_account_client import ManagedCodexAccountClient
from .codex_managed_inventory_store import CodexManagedInventoryStoreError, accepted_inventory_records, inventory_matches, policy_rel, record_ref
from .codex_managed_profile import prepare_codex_profile
from .codex_managed_profile_manifest import CodexProfileInventoryRef, capture_generated_profile_manifest, read_restart_manifest, verify_clean_profile_root
from .codex_managed_session import start_managed_codex_session
from .evidence_json import canonical_bytes, canonical_sha256, strict_load_json
from .private_artifact_fs import PrivateArtifactError, open_artifact_root
BOOTSTRAP_RECEIPT_SCHEMA = 'flywheel.codex-managed-no-auth-bootstrap-receipt/v1'
BASELINE_REF_SCHEMA = 'flywheel.codex-managed-baseline-inventory-ref/v1'
_HEX64 = re.compile(r'[0-9a-f]{64}')
_MAX_RECORD = 262_144
class CodexManagedInventoryLifecycleError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)
class CodexManagedInventoryLifecycle:
    def __init__(self, *, state_root: Path, policy_root: Path, workspace: Path,
            executable: Path, executable_sha256: str, configured_version: str, version_provenance: str, model: str,
            start_session=start_managed_codex_session):
        self.state_root = _absolute_dir(state_root)
        self.policy_root = _absolute_dir(policy_root)
        self.workspace = _absolute_dir(workspace)
        self.executable = Path(executable).absolute()
        self.executable_sha256 = _hex(executable_sha256, 'BASELINE_INVALID_EXECUTABLE')
        self.configured_version = _text(configured_version, 'BASELINE_INVALID_VERSION')
        self.version_provenance = _text(version_provenance, 'BASELINE_INVALID_VERSION')
        self.model = _model(model)
        if not self.executable.is_absolute() or _sha256_file(self.executable) != self.executable_sha256:
            raise CodexManagedInventoryLifecycleError('BASELINE_EXECUTABLE_MISMATCH')
        self._start_session = start_session
        self._owned_sessions: list[Any] = []
        self._lock = threading.RLock()
    def ensure_baseline_inventory(self, owner_ref: str) -> CodexProfileInventoryRef:
        owner = safe_owner_ref(owner_ref)
        with self._lock:
            profile = prepare_codex_profile(self.state_root, workspace=self.workspace, owner_ref=owner)
            accepted = self._read_baseline(profile, owner)
            if accepted is not None:
                return accepted
            _require_clean_for_bootstrap(profile)
            session = self._start_session(profile, executable=self.executable, executable_sha256=self.executable_sha256, model=self.model, inventory=None)
            self._remember(session)
            if not self._close_and_release(session):
                raise CodexManagedInventoryLifecycleError('BASELINE_CLEANUP_REQUIRED')
            receipt_sha = self._write_bootstrap_receipt(owner, profile, _cleanup_proof(session))
            ref = capture_generated_profile_manifest(profile, executable=self.executable, executable_sha256=self.executable_sha256,
                codex_version=self.configured_version, bootstrap_receipt_sha256=receipt_sha, policy_root=self.policy_root)
            return self.accept_verified_inventory(owner, ref, _profile=profile, _bootstrap_receipt_sha256=receipt_sha)
    def account_client_for_owner(self, *, owner_ref: str) -> ManagedCodexAccountBinding:
        owner = safe_owner_ref(owner_ref)
        with self._lock:
            inventory = self.ensure_baseline_inventory(owner)
            profile = prepare_codex_profile(self.state_root, workspace=self.workspace, owner_ref=owner)
            session = self._start_session(profile, executable=self.executable, executable_sha256=self.executable_sha256,
                model=self.model, inventory=inventory)
            self._remember(session)
            try:
                client = ManagedCodexAccountClient(session)
                return ManagedCodexAccountBinding(client=client, profile=profile, inventory=inventory,
                    executable=self.executable, executable_sha256=self.executable_sha256,
                    codex_version=self.configured_version, policy_root=self.policy_root)
            except Exception:
                self._close_and_release(session)
                raise
    def runtime_session_for_owner(self, *, owner_ref: str):
        owner = safe_owner_ref(owner_ref)
        with self._lock:
            profile = prepare_codex_profile(self.state_root, workspace=self.workspace, owner_ref=owner)
            inventory = self._read_baseline(profile, owner)
            if inventory is None:
                raise CodexManagedInventoryLifecycleError('AGENT_NATIVE_AUTH_REQUIRED')
            manifest = read_restart_manifest(inventory)
            if manifest.get('auth_extension') is None:
                raise CodexManagedInventoryLifecycleError('AGENT_NATIVE_AUTH_REQUIRED')
            self._validate_inventory(profile, inventory)
            session = self._start_session(profile, executable=self.executable, executable_sha256=self.executable_sha256,
                model=self.model, inventory=inventory)
            self._remember(session)
            return session, profile, inventory, manifest
    def accept_verified_inventory(self, owner_ref: str, inventory: CodexProfileInventoryRef, *,
            _profile=None, _bootstrap_receipt_sha256: str | None = None) -> CodexProfileInventoryRef:
        owner = safe_owner_ref(owner_ref)
        with self._lock:
            profile = _profile or prepare_codex_profile(self.state_root, workspace=self.workspace, owner_ref=owner)
            binding = self._binding(owner, profile)
            binding_sha = canonical_sha256(binding)
            self._validate_inventory(profile, inventory)
            self._reject_ambiguous_current(profile, owner, binding_sha, inventory.sha256)
            record = {'schema': BASELINE_REF_SCHEMA, 'binding_sha256': binding_sha, 'binding': binding,
                      'inventory': {'path': self._policy_rel(inventory.path), 'sha256': inventory.sha256}}
            self._write_record(_accepted_rel(binding_sha, inventory.sha256), record)
            if _bootstrap_receipt_sha256 is not None:
                record['bootstrap_receipt_sha256'] = _hex(_bootstrap_receipt_sha256, 'BASELINE_INVALID_RECEIPT')
                self._write_record(_baseline_rel(binding_sha), record)
            return inventory
    def shutdown(self) -> bool:
        with self._lock:
            ok = True
            for session in list(self._owned_sessions):
                if self._close_session(session):
                    self._owned_sessions.remove(session)
                else:
                    ok = False
            return ok
    def _binding(self, owner: str, profile) -> dict[str, Any]:
        return {
            'schema': 'flywheel.codex-managed-baseline-binding/v1',
            'owner_ref': owner,
            'workspace': {'path': str(self.workspace).lower(), 'identity': profile.workspace_identity.to_json_dict()},
            'profile': {'home_identity': profile.home_identity.to_json_dict(), 'config_sha256': profile.config_sha256},
            'executable': {'path': str(self.executable).lower(), 'sha256': self.executable_sha256},
            'codex': {'configured_version': self.configured_version, 'version_provenance': self.version_provenance,
                      'model': self.model},
        }

    def _read_baseline(self, profile, owner: str) -> CodexProfileInventoryRef | None:
        binding_sha = canonical_sha256(self._binding(owner, profile))
        records = self._accepted_records(binding_sha)
        if records:
            matches = self._matching_records(profile, owner, records)
            if len(matches) == 1:
                return matches[0]
            if len(matches) > 1:
                raise CodexManagedInventoryLifecycleError('BASELINE_INVENTORY_AMBIGUOUS')
            raise CodexManagedInventoryLifecycleError('BASELINE_ACCEPTED_INVENTORY_REQUIRED')
        rel = _baseline_rel(binding_sha)
        raw = self._read_policy(rel)
        if raw is None:
            return None
        try:
            record = strict_load_json(raw, max_bytes=_MAX_RECORD, max_depth=24)
            return self._accepted_from_record(profile, owner, record)
        except Exception as exc:
            raise CodexManagedInventoryLifecycleError('BASELINE_INVENTORY_REJECTED') from exc
    def _accepted_from_record(self, profile, owner: str, record: dict[str, Any]) -> CodexProfileInventoryRef:
        ref = self._record_ref(owner, profile, record)
        self._validate_inventory(profile, ref)
        return ref

    def _matching_records(self, profile, owner: str, records: list[dict[str, Any]]) -> list[CodexProfileInventoryRef]:
        refs = [self._record_ref(owner, profile, record) for record in records]
        return [ref for ref in refs if self._inventory_matches(profile, ref)]
    def _reject_ambiguous_current(self, profile, owner: str, binding_sha: str, sha256: str) -> None:
        records = self._accepted_records(binding_sha)
        if any(ref.sha256 != sha256 for ref in self._matching_records(profile, owner, records)):
            raise CodexManagedInventoryLifecycleError('BASELINE_INVENTORY_AMBIGUOUS')

    def _inventory_matches(self, profile, ref: CodexProfileInventoryRef) -> bool:
        try:
            return inventory_matches(profile, ref, policy_root=self.policy_root, executable=self.executable,
                                     executable_sha256=self.executable_sha256,
                                     configured_version=self.configured_version)
        except CodexManagedInventoryStoreError as exc:
            raise CodexManagedInventoryLifecycleError(exc.code) from exc
    def _validate_inventory(self, profile, inventory: CodexProfileInventoryRef) -> None:
        if not self._inventory_matches(profile, inventory):
            raise CodexManagedInventoryLifecycleError('BASELINE_INVENTORY_REJECTED')

    def _write_bootstrap_receipt(self, owner: str, profile, cleanup: dict[str, bool]) -> str:
        binding = self._binding(owner, profile)
        binding_sha = canonical_sha256(binding)
        receipt = {'schema': BOOTSTRAP_RECEIPT_SCHEMA, 'binding_sha256': binding_sha,
                   'binding': binding, 'cleanup': cleanup, 'auth': {'content_read': False, 'paths': []},
                   'does_not_prove': ['no provider authentication was attempted',
                                      'no future auth extension has been accepted']}
        payload = canonical_bytes(receipt)
        digest = hashlib.sha256(payload).hexdigest()
        self._write_bytes(f'codex-policy/{binding_sha}/bootstrap-receipt-{digest}.json', payload)
        return digest

    def _write_record(self, rel: str, record: dict[str, Any]) -> None:
        self._write_bytes(rel, canonical_bytes(record))
    def _write_bytes(self, rel: str, payload: bytes) -> None:
        try:
            with open_artifact_root(self.policy_root) as root:
                root.write_new_or_same(rel, payload)
        except PrivateArtifactError as exc:
            raise CodexManagedInventoryLifecycleError('BASELINE_POLICY_WRITE_' + exc.code) from exc
    def _read_policy(self, rel: str) -> bytes | None:
        try:
            with open_artifact_root(self.policy_root, writable=False) as root:
                return root.read_bytes(rel, max_bytes=_MAX_RECORD)
        except PrivateArtifactError as exc:
            if exc.code == 'NOT_FOUND':
                return None
            raise CodexManagedInventoryLifecycleError('BASELINE_POLICY_READ_' + exc.code) from exc
    def _accepted_records(self, binding_sha: str) -> list[dict[str, Any]]:
        try:
            return accepted_inventory_records(self.policy_root, binding_sha)
        except CodexManagedInventoryStoreError as exc:
            raise CodexManagedInventoryLifecycleError(exc.code) from exc
    def _record_ref(self, owner: str, profile, record: dict[str, Any]) -> CodexProfileInventoryRef:
        binding = self._binding(owner, profile)
        try:
            return record_ref(record, binding=binding, binding_sha=canonical_sha256(binding),
                              policy_root=self.policy_root)
        except CodexManagedInventoryStoreError as exc:
            raise CodexManagedInventoryLifecycleError(exc.code) from exc
    def _policy_rel(self, path: Path) -> str:
        try:
            return policy_rel(self.policy_root, path)
        except CodexManagedInventoryStoreError as exc:
            raise CodexManagedInventoryLifecycleError(exc.code) from exc

    def _remember(self, session: Any) -> None:
        if session not in self._owned_sessions:
            self._owned_sessions.append(session)
    def _close_and_release(self, session: Any) -> bool:
        ok = self._close_session(session)
        if ok and session in self._owned_sessions:
            self._owned_sessions.remove(session)
        return ok
    @staticmethod
    def _close_session(session: Any) -> bool:
        try:
            close = getattr(session, 'close')
            return close() is True
        except Exception:
            return False
def _require_clean_for_bootstrap(profile) -> None:
    try:
        verify_clean_profile_root(profile)
    except Exception as exc:
        raise CodexManagedInventoryLifecycleError('BASELINE_ACCEPTED_INVENTORY_REQUIRED') from exc
def _cleanup_proof(session: Any) -> dict[str, bool]:
    cleanup = getattr(session, 'cleanup', None)
    proof = {'process_exited': bool(getattr(cleanup, 'exited', False)),
             'job_closed': bool(getattr(cleanup, 'job_closed', False)),
             'stderr_drain_complete': bool(getattr(cleanup, 'stderr_drain_complete', False))}
    if not all(proof.values()):
        raise CodexManagedInventoryLifecycleError('BASELINE_CLEANUP_REQUIRED')
    return proof
def _absolute_dir(path: Path) -> Path:
    value = Path(path).absolute()
    if not value.is_absolute() or not value.is_dir():
        raise CodexManagedInventoryLifecycleError('BASELINE_INVALID_ROOT')
    return value
def _sha256_file(path: Path) -> str:
    try:
        with Path(path).open('rb') as source:
            return hashlib.file_digest(source, 'sha256').hexdigest()
    except OSError as exc:
        raise CodexManagedInventoryLifecycleError('BASELINE_EXECUTABLE_MISMATCH') from exc
def _hex(value: object, code: str) -> str:
    if type(value) is str and _HEX64.fullmatch(value):
        return value
    raise CodexManagedInventoryLifecycleError(code)
def _text(value: object, code: str) -> str:
    if type(value) is str and value.strip() and len(value) <= 256 and not _has_control(value):
        return value
    raise CodexManagedInventoryLifecycleError(code)
def _model(value: object) -> str:
    text = _text(value, 'BASELINE_INVALID_MODEL')
    if any(ch.isspace() or ord(ch) == 127 for ch in text):
        raise CodexManagedInventoryLifecycleError('BASELINE_INVALID_MODEL')
    return text
def _has_control(value: str) -> bool:
    return any(ord(ch) < 32 for ch in value)
def _baseline_rel(binding_sha: str) -> str:
    return f'codex-policy/{binding_sha}/baseline-inventory-ref.json'
def _accepted_rel(binding_sha: str, inventory_sha: str) -> str:
    return f'codex-policy/{binding_sha}/accepted-inventories/{inventory_sha}.json'
