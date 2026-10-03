import pytest

from harness.claude_session_contract import (
    ClaudeSessionContractError,
    ClaudeSessionLaunchConfig,
    build_claude_session_argv,
)


def test_resume_launch_keeps_persistence_and_acknowledgement_stream_enabled():
    argv = build_claude_session_argv(ClaudeSessionLaunchConfig(
        executable="claude.exe",
        resume_session_id="5b3f2c1a-8d4e-4f6b-9a7c-2e1d0f9b8a6c",
        replay_user_messages=True,
    ))

    assert "--resume=5b3f2c1a-8d4e-4f6b-9a7c-2e1d0f9b8a6c" in argv
    assert "--no-session-persistence" not in argv
    assert "--replay-user-messages" in argv


def test_nonpersistent_launch_is_explicit_and_cannot_resume():
    argv = build_claude_session_argv(ClaudeSessionLaunchConfig(
        executable="claude.exe", persist_session=False,
        replay_user_messages=False,
    ))

    assert "--no-session-persistence" in argv
    assert "--replay-user-messages" not in argv
    with pytest.raises(ClaudeSessionContractError) as caught:
        build_claude_session_argv(ClaudeSessionLaunchConfig(
            executable="claude.exe", resume_session_id="session-a",
            persist_session=False,
        ))
    assert caught.value.code == "resume_requires_persistence"


def test_fork_launch_is_bound_to_resume_identity():
    argv = build_claude_session_argv(ClaudeSessionLaunchConfig(
        executable="claude.exe", resume_session_id="session-a",
        fork_session=True,
    ))

    assert "--resume=session-a" in argv
    assert "--fork-session" in argv


def test_bypass_permission_mode_remains_refused_for_resume_launches():
    with pytest.raises(ClaudeSessionContractError) as caught:
        build_claude_session_argv(ClaudeSessionLaunchConfig(
            executable="claude.exe", resume_session_id="session-a",
            permission_mode="bypassPermissions",
        ))

    assert caught.value.code == "permission_bypass_refused"
