import json
from contextlib import contextmanager

import pytest

from harness import claude_provider_session_runtime as runtime_mod
from harness.claude_provider_session_runtime import (
    ClaudeManagedSessionPolicy,
    prepare_claude_runtime,
    retry_managed_claude_cleanup,
)
from harness.provider_session_contract import ProviderSessionError
from harness.provider_session_process import ProviderSessionProcessError
from tests.claude_provider_session_runtime_fixtures import (
    CapturingLauncher,
    FakeProcess,
    IncompleteCleanupProcess,
    PassiveLauncher,
    runtime_fixture,
)


def test_runtime_refuses_unpinned_or_drifted_executable(tmp_path):
    state, workspace, auth, executable, digest = runtime_fixture(tmp_path)

    for bad_hash in ("", digest.upper(), "0" * 64):
        with pytest.raises(ProviderSessionError) as caught:
            prepare_claude_runtime(
                state_root=state,
                workspace=workspace,
                owner_ref="owner-1",
                executable=executable,
                executable_sha256=bad_hash,
                auth_directory=auth,
            )
        assert caught.value.code in {"AGENT_NATIVE_RUNTIME_DISABLED", "AGENT_BINDING_DRIFT"}


@pytest.mark.parametrize("policy", [
    ClaudeManagedSessionPolicy(permission_mode="dontAsk"),
    ClaudeManagedSessionPolicy(permission_prompt_tool_name="mcp"),
    ClaudeManagedSessionPolicy(strict_mcp_config=False),
    ClaudeManagedSessionPolicy(mcp_config={"mcpServers": {"x": {}}}),
    ClaudeManagedSessionPolicy(settings={"disableAllHooks": False}),
    ClaudeManagedSessionPolicy(allowed_tools=("Bash",)),
])
def test_runtime_refuses_policy_that_bypasses_manual_stdio_custody(tmp_path, policy):
    state, workspace, auth, executable, digest = runtime_fixture(tmp_path)

    with pytest.raises(ProviderSessionError) as caught:
        prepare_claude_runtime(
            state_root=state,
            workspace=workspace,
            owner_ref="owner-1",
            executable=executable,
            executable_sha256=digest,
            auth_directory=auth,
            policy=policy,
        )

    assert caught.value.code == "AGENT_NATIVE_RUNTIME_DISABLED"


def test_runtime_refuses_missing_no_generation_isolation_controls(tmp_path):
    state, workspace, auth, executable, digest = runtime_fixture(tmp_path)
    cases = (
        {"safe_mode": False},
        {"restricted": False},
        {"setting_sources": ("user",)},
        {"tools": ("Read",)},
    )

    for overrides in cases:
        with pytest.raises(ProviderSessionError) as caught:
            prepare_claude_runtime(
                state_root=state,
                workspace=workspace,
                owner_ref="owner-1",
                executable=executable,
                executable_sha256=digest,
                auth_directory=auth,
                policy=ClaudeManagedSessionPolicy(**overrides),
            )
        assert caught.value.code == "AGENT_NATIVE_RUNTIME_DISABLED"


@pytest.mark.parametrize("project_setting", [".claude", ".mcp.json"])
def test_runtime_refuses_workspace_project_settings(tmp_path, project_setting):
    state, workspace, auth, executable, digest = runtime_fixture(tmp_path)
    target = workspace / project_setting
    if "." in project_setting[1:]:
        target.write_text("{}", encoding="utf-8")
    else:
        target.mkdir()

    with pytest.raises(ProviderSessionError) as caught:
        prepare_claude_runtime(
            state_root=state,
            workspace=workspace,
            owner_ref="owner-1",
            executable=executable,
            executable_sha256=digest,
            auth_directory=auth,
        )

    assert caught.value.code == "AGENT_NATIVE_RUNTIME_DISABLED"


def test_runtime_writes_owned_policy_without_copying_auth_material(tmp_path):
    state, workspace, auth, executable, digest = runtime_fixture(tmp_path)
    (auth / "token.json").write_text("secret-provider-token", encoding="utf-8")

    runtime = prepare_claude_runtime(
        state_root=state,
        workspace=workspace,
        owner_ref="owner-1",
        executable=executable,
        executable_sha256=digest,
        auth_directory=auth,
    )

    assert runtime.admitted is False
    assert "provider_policy_not_attested" in runtime.limitations
    assert "no_tool_initialization_only" in runtime.limitations
    assert "production_tool_approval_not_proven" in runtime.limitations
    assert json.loads((runtime.profile_home / "settings.json").read_text()) == {
        "disableAllHooks": True,
    }
    assert json.loads((runtime.profile_home / "mcp.json").read_text()) == {"mcpServers": {}}
    assert not any(path.name == "token.json" for path in runtime.profile_home.rglob("*"))
    env = runtime.environment()
    assert env["CLAUDE_CONFIG_DIR"] == str(auth)
    assert env["HOME"] == str(runtime.profile_home / "runtime")


def test_runtime_start_client_initializes_only_through_manual_stdio_launcher(tmp_path):
    state, workspace, auth, executable, digest = runtime_fixture(tmp_path)
    runtime = prepare_claude_runtime(
        state_root=state,
        workspace=workspace,
        owner_ref="owner-1",
        executable=executable,
        executable_sha256=digest,
        auth_directory=auth,
    )
    process = FakeProcess()
    launcher = CapturingLauncher(process)

    client = runtime.start_client(
        model="claude-test-model",
        launcher=launcher,
        initialize_timeout=0.5,
    )

    assert client.session_id == ""
    assert len(launcher.calls) == 1
    call = launcher.calls[0]
    assert call["cwd"] == str(workspace)
    assert call["env"]["CLAUDE_CONFIG_DIR"] == str(auth)
    assert call["argv"][0] == str(executable)
    assert "--permission-mode=manual" in call["argv"]
    assert call["argv"][call["argv"].index("--permission-prompt-tool") + 1] == "stdio"
    assert "--safe-mode" in call["argv"]
    assert "--restricted" in call["argv"]
    assert "--setting-sources=" in call["argv"]
    assert "--tools=" in call["argv"]
    assert "--strict-mcp-config" in call["argv"]
    assert call["argv"][call["argv"].index("--mcp-config") + 1] == '{"mcpServers":{}}'
    assert call["argv"][call["argv"].index("--settings") + 1] == '{"disableAllHooks":true}'
    assert call["argv"][call["argv"].index("--disallowedTools") + 1] == "mcp__*"
    assert "--disable-slash-commands" in call["argv"]
    assert "--no-chrome" in call["argv"]
    assert "--replay-user-messages" not in call["argv"]
    assert [m["type"] for m in process.stdin.wait_messages(1)] == ["control_request"]
    assert client.close() is True


def test_runtime_launch_policy_is_sealed_against_post_prepare_mutation(tmp_path):
    state, workspace, auth, executable, digest = runtime_fixture(tmp_path)
    mcp_config = {"mcpServers": {}}
    settings = {"disableAllHooks": True}
    setting_sources = []
    tools = []
    allowed_tools = []
    disallowed_tools = ["mcp__*"]
    runtime = prepare_claude_runtime(
        state_root=state,
        workspace=workspace,
        owner_ref="owner-1",
        executable=executable,
        executable_sha256=digest,
        auth_directory=auth,
        policy=ClaudeManagedSessionPolicy(
            mcp_config=mcp_config,
            settings=settings,
            setting_sources=setting_sources,
            tools=tools,
            allowed_tools=allowed_tools,
            disallowed_tools=disallowed_tools,
        ),
    )
    mcp_config["mcpServers"]["late"] = {"command": "late-tool"}
    settings["disableAllHooks"] = False
    setting_sources.append("user")
    tools.append("Read")
    allowed_tools.append("Bash")
    disallowed_tools.clear()
    process = FakeProcess()
    launcher = CapturingLauncher(process)

    client = runtime.start_client(
        model="claude-test-model",
        launcher=launcher,
        initialize_timeout=0.5,
    )

    argv = launcher.calls[0]["argv"]
    assert "--setting-sources=" in argv
    assert "--tools=" in argv
    assert argv[argv.index("--mcp-config") + 1] == '{"mcpServers":{}}'
    assert argv[argv.index("--settings") + 1] == '{"disableAllHooks":true}'
    assert "--allowedTools" not in argv
    assert argv[argv.index("--disallowedTools") + 1] == "mcp__*"
    assert client.close() is True


def test_runtime_keeps_custody_after_prelaunch_owned_process_error(tmp_path, monkeypatch):
    state, workspace, auth, executable, digest = runtime_fixture(tmp_path)
    runtime = prepare_claude_runtime(
        state_root=state,
        workspace=workspace,
        owner_ref="owner-1",
        executable=executable,
        executable_sha256=digest,
        auth_directory=auth,
    )
    process, released = IncompleteCleanupProcess(), []

    @contextmanager
    def fake_lease(_profile):
        try:
            yield lambda: None
        finally:
            released.append("released")

    def failing_launcher(_argv, _cwd, _env):
        error = ProviderSessionProcessError("provider session prelaunch check failed")
        error.owned_process = process
        raise error

    monkeypatch.setattr(runtime_mod, "lease_claude_profile", fake_lease)

    with pytest.raises(ProviderSessionError) as caught:
        runtime.start_client(model="claude-test-model", launcher=failing_launcher,
                             initialize_timeout=0.05)

    assert caught.value.code == "AGENT_NATIVE_CLEANUP_REQUIRED"
    assert released == []
    assert retry_managed_claude_cleanup() is True
    assert released == ["released"]


@pytest.mark.parametrize("process", [
    IncompleteCleanupProcess(),
    IncompleteCleanupProcess(missing_stdout=True),
])
def test_runtime_keeps_custody_after_failed_start_without_cleanup_proof(
        tmp_path, monkeypatch, process):
    state, workspace, auth, executable, digest = runtime_fixture(tmp_path)
    runtime = prepare_claude_runtime(
        state_root=state,
        workspace=workspace,
        owner_ref="owner-1",
        executable=executable,
        executable_sha256=digest,
        auth_directory=auth,
    )
    released = []

    @contextmanager
    def fake_lease(_profile):
        try:
            yield lambda: None
        finally:
            released.append("released")

    monkeypatch.setattr(runtime_mod, "lease_claude_profile", fake_lease)

    with pytest.raises(ProviderSessionError) as caught:
        runtime.start_client(
            model="claude-test-model",
            launcher=PassiveLauncher(process),
            initialize_timeout=0.05,
        )

    assert caught.value.code == "AGENT_NATIVE_CLEANUP_REQUIRED"
    assert released == []
    assert retry_managed_claude_cleanup() is True
    assert released == ["released"]
