from harness.gateway_worker_env import minimal_worker_env


def test_worker_env_uses_server_paths_not_ambient_home(monkeypatch, tmp_path):
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "ambient-profile"))
    monkeypatch.setenv("HOME", str(tmp_path / "ambient-home"))
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path / "ambient-fw-home"))
    monkeypatch.setenv("FLYWHEEL_RUN_ROOT", str(tmp_path / "ambient-run"))

    env = minimal_worker_env(tmp_path / "repo", run_root=tmp_path / "run",
        state_root=tmp_path / "state")

    profile = str(tmp_path / "state" / "worker-profile")
    assert env["PYTHONPATH"] == str(tmp_path / "repo")
    assert env["FLYWHEEL_HOME"] == str(tmp_path / "state")
    assert env["FLYWHEEL_RUN_ROOT"] == str(tmp_path / "run")
    assert env["HOME"] == profile and env["USERPROFILE"] == profile
    assert not any("ambient-" in value for value in env.values())


def test_worker_env_without_state_root_uses_run_root_private_home(tmp_path):
    env = minimal_worker_env(tmp_path / "repo", run_root=tmp_path / "run")

    assert env["FLYWHEEL_HOME"] == str(tmp_path / "run" / "worker-home")
    assert env["HOME"] == str(tmp_path / "run" / "worker-home" / "worker-profile")
