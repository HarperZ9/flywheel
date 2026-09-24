"""Dedicated Codex profile preparation; no credential reads or copying.

Configuration custody is a Windows file lease, not a process sandbox. A runtime
must still inspect effective provider policy and verify tool enforcement.
"""
from __future__ import annotations

from contextlib import contextmanager, ExitStack
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re

from .codex_managed_profile_manifest import (
    CodexProfileManifestError,
    verify_clean_profile_root,
    verify_restart_inventory,
)
from .evidence_json import canonical_sha256
from .gateway_cli_runtime import session_env
from .private_artifact_fs import ArtifactIdentity, open_artifact_root


class CodexProfileError(RuntimeError):
    pass


@dataclass(frozen=True)
class CodexManagedProfile:
    home: Path
    workspace: Path
    home_identity: ArtifactIdentity
    workspace_identity: ArtifactIdentity
    config_sha256: str


def _config(workspace: Path) -> bytes:
    trust_key = json.dumps(str(workspace).lower())
    return ('''model_provider = "openai"
approval_policy = "on-request"
approvals_reviewer = "user"
sandbox_mode = "read-only"
web_search = "disabled"
notify = []
mcp_servers = {}
project_doc_max_bytes = 0
cli_auth_credentials_store = "file"
[features]
hooks = false
apps = false
plugins = false
[analytics]
enabled = false
''' + f'[projects.{trust_key}]\ntrust_level = "untrusted"\n').encode('utf-8')


def prepare_codex_profile(state_root: Path, *, workspace: Path,
                          owner_ref: str) -> CodexManagedProfile:
    state_root, workspace = Path(state_root), Path(workspace)
    if (not state_root.is_absolute() or not workspace.is_absolute()
            or type(owner_ref) is not str or not owner_ref.strip()
            or len(owner_ref) > 256 or any(ord(c) < 32 for c in owner_ref)):
        raise CodexProfileError('PROFILE_INVALID_REQUEST')
    state_root, workspace = state_root.absolute(), workspace.absolute()
    if state_root.is_relative_to(workspace) or workspace.is_relative_to(state_root):
        raise CodexProfileError('PROFILE_PATH_OVERLAP')
    try:
        with open_artifact_root(workspace, writable=False) as work, \
                open_artifact_root(state_root) as state:
            identity = work.identity
            key = canonical_sha256({'owner': owner_ref, 'workspace': str(workspace).lower(),
                                    'identity': identity.to_json_dict()})
            rel = 'codex-managed/' + key
            config = _config(workspace)
            state.write_new_or_same(rel + '/config.toml', config)
            state.write_new_or_same(rel + '/runtime/Temp/.flywheel-owned', b'')
            home = state_root / rel
            with open_artifact_root(home, writable=False) as profile:
                return CodexManagedProfile(home, workspace, profile.identity, identity,
                                           hashlib.sha256(config).hexdigest())
    except CodexProfileError:
        raise
    except Exception:
        raise CodexProfileError('PROFILE_CONFLICT') from None


def codex_profile_environment(profile: CodexManagedProfile) -> dict[str, str]:
    return session_env('codex-cli', str(profile.home), profile.home / 'runtime')


@contextmanager
def lease_codex_profile(profile: CodexManagedProfile, *, executable: Path,
                        executable_sha256: str, inventory=None):
    """Pin reviewed config/executable and ancestors until owned process cleanup.

    The yielded no-arg callback rechecks root admission immediately before a
    suspended provider process is resumed. This does not prevent same-user root
    writes after resume; config and executable pins remain active for the lease.
    """
    if os.name != 'nt':
        raise CodexProfileError('PROFILE_PLATFORM_UNSUPPORTED')
    if not re.fullmatch('[0-9a-f]{64}', executable_sha256 or ''):
        raise CodexProfileError('PROFILE_INVALID_REQUEST')
    executable = Path(executable)
    if not executable.is_absolute():
        raise CodexProfileError('PROFILE_INVALID_REQUEST')
    with ExitStack() as stack:
        try:
            home = stack.enter_context(open_artifact_root(profile.home, writable=True,
                                                         expected=profile.home_identity))
            stack.enter_context(open_artifact_root(profile.workspace, writable=True,
                                                   expected=profile.workspace_identity))
            stack.enter_context(open_artifact_root(profile.home.parent, writable=True))
            _verify_profile_admission(profile, executable=executable,
                                      executable_sha256=executable_sha256, inventory=inventory)
            stack.enter_context(_pin_file(home, profile.home / 'config.toml', profile.config_sha256,
                                          single_link=True))
            binary_root = stack.enter_context(open_artifact_root(executable.parent,
                                                                  writable=True))
            stack.enter_context(_pin_file(binary_root, executable, executable_sha256))
        except CodexProfileError:
            raise
        except Exception:
            raise CodexProfileError('PROFILE_BINDING_DRIFT') from None
        yield lambda: _verify_profile_admission(profile, executable=executable,
            executable_sha256=executable_sha256, inventory=inventory)


def _verify_profile_admission(profile: CodexManagedProfile, *, executable: Path,
                              executable_sha256: str, inventory) -> None:
    try:
        if inventory is None:
            verify_clean_profile_root(profile)
        else:
            verify_restart_inventory(profile, inventory, executable=executable,
                                     executable_sha256=executable_sha256)
    except CodexProfileManifestError as exc:
        if exc.code == 'MANIFEST_ROOT_MISMATCH':
            raise CodexProfileError('PROFILE_UNREVIEWED_SETTINGS') from exc
        raise CodexProfileError('PROFILE_BINDING_DRIFT') from exc


@contextmanager
def _pin_file(root, path: Path, expected_hash: str, *, single_link: bool = False):
    from . import private_artifact_fs_windows_api as win
    options = (win.FILE_NON_DIRECTORY_FILE | win.FILE_OPEN_REPARSE_POINT |
               win.FILE_SYNCHRONOUS_IO_NONALERT)
    with root.borrow_descriptor() as parent:
        handle = win.nt_create_relative(parent.handle, path.name,
            win.GENERIC_READ | win.SYNCHRONIZE, win.FILE_SHARE_READ, win.FILE_OPEN, options)
    try:
        info = win.handle_info(handle)
        if (info.dwFileAttributes & (win.FILE_ATTRIBUTE_DIRECTORY | win.FILE_ATTRIBUTE_REPARSE_POINT)
                or single_link and info.nNumberOfLinks != 1):
            raise CodexProfileError('PROFILE_BINDING_DRIFT')
        # Root ancestors and the file are pinned against replacement/write now.
        # The matching absolute path now cannot be replaced while streaming its
        # bytes. Streaming avoids allocating the complete executable in memory.
        size = (info.nFileSizeHigh << 32) | info.nFileSizeLow
        if size > 1024 * 1024 * 1024:
            raise CodexProfileError('PROFILE_BINDING_DRIFT')
        with path.open('rb') as source:
            digest = hashlib.file_digest(source, 'sha256').hexdigest()
        if digest != expected_hash:
            raise CodexProfileError('PROFILE_BINDING_DRIFT')
        yield
    finally:
        win.close_handle(handle)
