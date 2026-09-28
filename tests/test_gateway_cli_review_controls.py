"""Regression controls for the independent native CLI review."""
import json
import time
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
import pytest

from harness.gateway_operation import GatewayOperationError, canonicalize_operation


class Completed:
    def __init__(self): self.closed = False
    def resume(self): return True
    def stdout_snapshot(self):
        return b'{"type":"result","is_error":false,"subtype":"success","result":"ok","num_turns":1}\n', False
    def capture_overflow(self): return False
    def wait(self, timeout):
        return SimpleNamespace(returncode=0, timed_out=False, malformed_output=False,
            stdout=self.stdout_snapshot()[0].decode())
    def close(self): self.closed = True


def test_parent_home_never_becomes_child_profile_and_new_profile_exists(tmp_path, monkeypatch):
    from harness import gateway_cli_execution as execution
    from harness.gateway_cli_profiles import session_profile
    parent_home = tmp_path / 'private-parent'; parent_home.mkdir()
    monkeypatch.setenv('HOME', str(parent_home))
    monkeypatch.setenv('USERPROFILE', str(parent_home))
    monkeypatch.setattr(execution, 'verify_runtime', lambda _: None)
    monkeypatch.setattr(execution, 'pin_runtime', lambda _: nullcontext())
    binding = {'model': {'model_id': 'fixture'}, 'budget': {'max_steps': 2},
        'cli_runtime': {'executable': 'fixture.exe', 'auth_directory': str(tmp_path / 'auth')},
        'cli_session': session_profile('claude-cli', allow_write=False, allow_exec=False)}
    seen = []
    def launch(*args, **kwargs):
        env = kwargs['env']; home = Path(env['HOME'])
        assert home.is_dir() and home != parent_home and home != tmp_path
        assert env['USERPROFILE'] == str(home)
        assert env['CLAUDE_CONFIG_DIR'] == str(tmp_path / 'auth')
        seen.append(home)
        return Completed()
    for _ in range(2):
        execution.run_cli_session('goal', binding, tmp_path, time.monotonic() + 5,
            lambda _: None, launcher=launch)
    assert seen[0] != seen[1]


def test_codex_refused_even_without_project_config_and_before_runtime_probe(tmp_path, monkeypatch):
    from harness import gateway_cli_binding
    from harness.gateway_agent_binding import freeze_agent_binding
    monkeypatch.setattr(gateway_cli_binding, 'freeze_runtime', lambda *a: pytest.fail('unavailable profile probed CLI'))
    op = canonicalize_operation('agent.run', {'goal': 'Inspect fixture', 'endpoint': 'codex-cli',
        'execution_mode': 'native_cli_session', 'model': 'exact', 'root': str(tmp_path),
        'max_steps': 2, 'allow_write': False, 'allow_exec': True,
        'stream': True, 'data_refs': [], 'credential_refs': []})
    with pytest.raises(GatewayOperationError, match='AGENT_CLI_PROFILE_UNSUPPORTED'):
        freeze_agent_binding(op, tmp_path)


def test_codex_documented_summary_text_retained_but_opaque_fields_omitted():
    from harness.gateway_cli_events import NativeEvents
    emitted = []
    parser = NativeEvents('codex-cli', ['command_execution'], emitted.append, max_steps=2)
    parser.feed(json.dumps({'type': 'item.completed', 'item': {'id': 'r', 'type': 'reasoning',
        'text': 'Provider visible summary', 'encrypted_content': 'opaque-never-retain'}}))
    assert emitted == [{'type': 'cli_reasoning_summary', 'source': 'codex-cli',
        'item_id': 'r', 'text': 'Provider visible summary'}]
    assert 'opaque-never-retain' not in json.dumps(emitted)


def test_unattested_summary_shape_has_explicit_private_omission():
    from harness.gateway_cli_events import NativeEvents
    emitted = []
    parser = NativeEvents('codex-cli', [], emitted.append, max_steps=2)
    parser.feed(json.dumps({'type': 'item.completed', 'item': {'id': 'r', 'type': 'reasoning',
        'summary': 'Unattested field content'}}))
    assert emitted == [{'type': 'cli_omission', 'source': 'codex-cli',
        'reason': 'PROVIDER_SUMMARY_SHAPE_UNSUPPORTED'}]
    assert 'Unattested field content' not in json.dumps(emitted)


def test_profile_is_allocated_beneath_pinned_private_state(tmp_path):
    from harness.gateway_cli_profile_home import owned_profile_home
    from harness.private_artifact_fs import root_identity
    state = tmp_path / 'private-state'; state.mkdir()
    with owned_profile_home(state_root=state, state_identity=root_identity(state)) as profile:
        assert profile.parent == state
        assert (profile / 'Temp').is_dir()
        assert (profile / 'AppData/Local').is_dir()
        assert (profile / 'AppData/Roaming').is_dir()
    assert profile.is_dir()  # private scratch retention, no unsafe recursive deletion


def test_replaced_private_state_cannot_receive_a_new_cli_profile(tmp_path):
    from harness.gateway_cli_profile_home import owned_profile_home
    from harness.private_artifact_fs import root_identity
    state = tmp_path / 'private-state'; state.mkdir()
    expected = root_identity(state)
    state.rename(tmp_path / 'original-state'); state.mkdir()
    with pytest.raises(GatewayOperationError, match='AGENT_CLI_UNAVAILABLE'):
        with owned_profile_home(state_root=state, state_identity=expected):
            pytest.fail('replaced state admitted')
    assert list(state.iterdir()) == []


def test_codex_old_binding_is_not_reusable_after_profile_withdrawal():
    from harness.gateway_agent_binding import validate_agent_binding
    folder = Path(__file__).parent / 'fixtures' / 'native_cli_session'
    binding = json.loads((folder / 'codex-read-binding.json').read_text())
    op = canonicalize_operation('agent.run', json.loads((folder / 'codex-read-operation.json').read_text()))
    with pytest.raises(GatewayOperationError, match='AGENT_BINDING_DRIFT'):
        validate_agent_binding(binding, op)


def test_codex_unavailable_is_checked_before_launch_even_with_late_config(tmp_path, monkeypatch):
    from harness import gateway_cli_execution as execution
    from harness.gateway_cli_profiles import session_profile
    monkeypatch.setattr(execution, 'verify_runtime', lambda _: pytest.fail('runtime accessed for unavailable profile'))
    binding = {'cli_runtime': {},
        'cli_session': session_profile('codex-cli', allow_write=False, allow_exec=True)}
    def launch(*args, **kwargs):
        (tmp_path / '.codex').mkdir()
        pytest.fail('unavailable profile launched')
    with pytest.raises(GatewayOperationError, match='AGENT_CLI_PROFILE_UNSUPPORTED'):
        execution.run_cli_session('goal', binding, tmp_path, time.monotonic() + 5,
            lambda _: None, launcher=launch)
    assert not (tmp_path / '.codex').exists()
