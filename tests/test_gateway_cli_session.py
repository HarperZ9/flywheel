"""Native CLI controls are real invocation contracts, not text-tool receipts."""
import json
from pathlib import Path
import pytest

from harness.gateway_operation import GatewayOperationError


def test_claude_profile_confines_native_file_tools_and_preserves_auth():
    from harness.gateway_cli_profiles import session_profile, session_argv
    profile = session_profile('claude-cli', allow_write=True, allow_exec=False)
    argv = session_argv('claude.exe', profile, 'claude-exact', Path('workspace'), 4)
    assert '--restricted' in argv and '--safe-mode' in argv
    assert argv[argv.index('--model') + 1] == 'claude-exact'
    assert argv[argv.index('--tools') + 1] == 'Read,Glob,Grep,Edit,Write'
    assert '--bare' not in argv and '--dangerously-skip-permissions' not in argv
    assert '--no-session-persistence' in argv
    assert profile['controls']['max_tokens'] == 'unsupported'


def test_unconfined_claude_commands_are_not_admitted():
    from harness.gateway_cli_profiles import session_profile
    with pytest.raises(GatewayOperationError, match='AGENT_CLI_PERMISSION_UNSUPPORTED'):
        session_profile('claude-cli', allow_write=True, allow_exec=True)


def test_native_events_keep_results_and_drop_hidden_reasoning():
    from harness.gateway_cli_events import NativeEvents
    emitted = []
    events = NativeEvents('claude-cli', ['Read'], emitted.append, max_steps=4)
    events.feed(json.dumps({'type': 'assistant', 'message': {'model': 'reported-model',
        'content': [{'type': 'thinking', 'thinking': 'opaque-do-not-retain'},
                    {'type': 'tool_use', 'id': 'tool1', 'name': 'Read',
                     'input': {'file_path': 'fixture.txt'}}]}}))
    events.feed(json.dumps({'type': 'user', 'message': {'content': [
        {'type': 'tool_result', 'tool_use_id': 'tool1', 'content': 'fixture contents'}]}}))
    events.feed(json.dumps({'type': 'result', 'subtype': 'success',
        'is_error': False, 'result': 'Read fixture', 'num_turns': 1}))
    result = events.finish()
    assert result['final'] == 'Read fixture'
    assert result['model_observed'] == 'reported-model'
    assert 'opaque-do-not-retain' not in json.dumps(emitted)
    assert any(e['type'] == 'cli_tool_result' for e in emitted)


def test_success_text_without_terminal_event_is_not_success():
    from harness.gateway_cli_events import NativeEvents
    events = NativeEvents('codex-cli', ['command_execution'], lambda e: None, max_steps=4)
    events.feed(json.dumps({'type': 'item.completed', 'item': {
        'type': 'agent_message', 'id': 'msg', 'text': 'All done'}}))
    with pytest.raises(GatewayOperationError, match='AGENT_CLI_INCOMPLETE'):
        events.finish()


def test_disallowed_native_tool_is_a_failure_not_an_outer_tool_call():
    from harness.gateway_cli_events import NativeEvents
    events = NativeEvents('claude-cli', ['Read'], lambda e: None, max_steps=4)
    with pytest.raises(GatewayOperationError, match='AGENT_CLI_PERMISSION_UNSUPPORTED'):
        events.feed(json.dumps({'type': 'assistant', 'message': {'content': [
            {'type': 'tool_use', 'id': 'bad', 'name': 'Bash', 'input': {}}]}}))


@pytest.mark.parametrize('line', ['{"type":"system","type":"result"}',
    '{"type":"system","x":NaN}', '[]', 'broken'])
def test_invalid_json_never_becomes_a_trace_event(line):
    from harness.gateway_cli_events import NativeEvents
    emitted = []
    events = NativeEvents('claude-cli', ['Read'], emitted.append, max_steps=2)
    with pytest.raises(GatewayOperationError, match='AGENT_CLI_PROTOCOL_ERROR'):
        events.feed(line)
    assert not emitted


def test_codex_profile_never_requests_elevation_or_native_turn_bound():
    from harness.gateway_cli_profiles import session_profile, session_argv
    profile = session_profile('codex-cli', allow_write=True, allow_exec=True)
    argv = session_argv('codex.exe', profile, 'exact-model', Path('workspace'), 2)
    assert 'windows.sandbox="unelevated"' in argv
    assert argv[argv.index('--sandbox') + 1] == 'workspace-write'
    assert profile['controls']['max_steps'] == 'unsupported'
    assert 'READ_SCOPE_NOT_WORKSPACE_CONFINED' in profile['limitations']
