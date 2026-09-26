"""EN-C4: a native CLI session names the profile directory it made, so a
later deletion of the trace can find it. Name only, never a path."""
import time

from tests.test_gateway_cli_execution import FixtureProcess


def test_the_session_emits_the_profile_directory_name_first(tmp_path, monkeypatch):
    from harness import gateway_cli_execution as execution
    from harness.gateway_cli_profiles import session_profile
    monkeypatch.setattr(execution, "verify_runtime", lambda r: None)
    monkeypatch.setattr(execution, "pin_runtime",
                        lambda r: __import__("contextlib").nullcontext())
    monkeypatch.setattr(execution, "check_configuration_boundary", lambda *a: None)
    binding = {"endpoint": {"name": "claude-cli"}, "model": {"model_id": "exact"},
               "budget": {"max_steps": 3},
               "cli_session": session_profile("claude-cli", allow_write=False, allow_exec=False),
               "cli_runtime": {"executable": "fixture.exe", "auth_directory": str(tmp_path)}}
    state = tmp_path / "state"
    state.mkdir()
    emitted = []
    process = FixtureProcess({}, [{"type": "result", "is_error": False, "subtype": "success",
                                   "result": "Done", "num_turns": 1}])
    execution.run_cli_session("Read", binding, tmp_path, time.monotonic() + 5, emitted.append,
                              launcher=lambda *a, **k: process, state_root=state)
    first = emitted[0]
    assert first["type"] == "cli_profile"
    assert first["profile_dir"].startswith("native-cli-profile-")
    assert "/" not in first["profile_dir"] and "\\" not in first["profile_dir"]
    assert (state / first["profile_dir"]).is_dir()
