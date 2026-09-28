"""Native executable custody and narrowly passed official-client auth location."""
import os
from contextlib import contextmanager
from pathlib import Path
import re
from .claude_cli_auth import _identity, resolve_official_cli
from .cross_harness_cli_identity import resolve_binary, validate_executable_path
from .cross_harness_process import start_owned_process
from .evidence_json import canonical_sha256
from .gateway_operation import GatewayOperationError
from .private_artifact_fs import root_identity, open_artifact_root, ArtifactIdentity

_SYSTEM = {'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATHEXT', 'PATH', 'TEMP', 'TMP'}
_CACHE = {}


def _probe(executable, args, env):
    child = start_owned_process([executable, *args], cwd=Path(executable).parent,
        stdin_bytes=b'', env=env, hide_window=True)
    try:
        if not child.resume(): raise ValueError
        out = child.wait(8)
        if out is None: raise ValueError
        return out
    finally:
        child.close()


def session_env(provider, auth_directory, synthetic_home):
    env = {k: v for k, v in os.environ.items() if k.upper() in _SYSTEM}
    env.update(HOME=str(synthetic_home), USERPROFILE=str(synthetic_home))
    env.update(TEMP=str(Path(synthetic_home) / 'Temp'), TMP=str(Path(synthetic_home) / 'Temp'),
        APPDATA=str(Path(synthetic_home) / 'AppData/Roaming'),
        LOCALAPPDATA=str(Path(synthetic_home) / 'AppData/Local'))
    env['CLAUDE_CONFIG_DIR' if provider == 'claude-cli' else 'CODEX_HOME'] = auth_directory
    return env


def freeze_runtime(provider, profile):
    """No account files are read. Only CLI help/version and directory identities."""
    if os.name != 'nt': raise GatewayOperationError('AGENT_CLI_UNAVAILABLE')
    if provider == 'claude-cli':
        resolved = resolve_official_cli(content_identity=True)
        executable = resolved.get('path', '') if resolved.get('ok') else ''
    else:
        executable = resolve_binary(('codex.exe',))
    if validate_executable_path(executable):
        raise GatewayOperationError('AGENT_CLI_UNAVAILABLE')
    identity = _identity(executable, content=True)
    key = provider, executable, identity
    if key not in _CACHE:
        probe_env = {k: v for k, v in os.environ.items() if k.upper() in _SYSTEM}
        outputs = []
        for args in (['--version'], ['--help'] if provider == 'claude-cli' else ['exec', '--help']):
            try:
                out = _probe(executable, args, probe_env)
            except Exception:
                raise GatewayOperationError('AGENT_CLI_UNAVAILABLE') from None
            if out.returncode or out.timed_out or out.malformed_output:
                raise GatewayOperationError('AGENT_CLI_UNAVAILABLE')
            outputs.append(out.stdout)
        version = re.search(r'\b\d+\.\d+\.\d+\b', outputs[0])
        if not version or any(flag not in outputs[1] for flag in profile['required_flags']):
            raise GatewayOperationError('AGENT_CLI_PROFILE_UNSUPPORTED')
        _CACHE[key] = version.group(), canonical_sha256(outputs[1])
    home_key = 'CLAUDE_CONFIG_DIR' if provider == 'claude-cli' else 'CODEX_HOME'
    default = Path.home() / ('.claude' if provider == 'claude-cli' else '.codex')
    try:
        auth = Path(os.environ.get(home_key) or default).resolve(strict=True)
        auth_identity = root_identity(auth).to_json_dict()
    except Exception:
        raise GatewayOperationError('AGENT_CLI_AUTH_UNAVAILABLE') from None
    return {'executable': executable, 'identity': identity,
        'version': _CACHE[key][0], 'help_sha256': _CACHE[key][1],
        'auth_directory': str(auth), 'auth_directory_identity': auth_identity}


def verify_runtime(runtime):
    if (validate_executable_path(runtime['executable']) or
            _identity(runtime['executable'], content=True) != runtime['identity']):
        raise GatewayOperationError('AGENT_BINDING_DRIFT')
    try:
        if root_identity(Path(runtime['auth_directory'])).to_json_dict() != runtime['auth_directory_identity']:
            raise ValueError
    except Exception:
        raise GatewayOperationError('AGENT_BINDING_DRIFT') from None


@contextmanager
def pin_runtime(runtime):
    """Keep auth directory/ancestors and binary replacement pinned until exit."""
    from . import private_artifact_fs_windows_api as win
    executable = Path(runtime['executable'])
    handle = None
    try:
        with open_artifact_root(executable.parent, writable=False), open_artifact_root(
                runtime['auth_directory'], writable=False,
                expected=ArtifactIdentity.from_json_dict(runtime['auth_directory_identity'])):
            handle = win.create_file(str(executable), win.GENERIC_READ, win.FILE_SHARE_READ,
                win.OPEN_EXISTING, win.FILE_FLAG_OPEN_REPARSE_POINT)
            info = win.handle_info(handle)
            if info.dwFileAttributes & (win.FILE_ATTRIBUTE_DIRECTORY | win.FILE_ATTRIBUTE_REPARSE_POINT):
                raise ValueError
            verify_runtime(runtime)
            yield
    except GatewayOperationError:
        raise
    except Exception:
        raise GatewayOperationError('AGENT_CLI_UNAVAILABLE') from None
    finally:
        if handle is not None: win.close_handle(handle)


def check_configuration_boundary(provider, root):
    """Codex direct sessions lack an admitted project-config isolation control.

    An absence check can race creation and is not authority. Keep the draft
    profile unavailable until a documented control or sealed workspace exists.
    """
    if provider == 'codex-cli':
        raise GatewayOperationError('AGENT_CLI_PROFILE_UNSUPPORTED')
