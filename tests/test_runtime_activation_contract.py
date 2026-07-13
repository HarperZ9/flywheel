from scripts.run_runtime_activation_contract import build_contract, render_markdown


def test_runtime_contract_records_paths_and_env_presence(tmp_path, monkeypatch):
    package = tmp_path / "package"
    repo = tmp_path / "repo"
    model_root = tmp_path / "models"
    (package / "config").mkdir(parents=True)
    repo.mkdir()
    model_root.mkdir()
    (package / "config" / "model_endpoint_profiles.local.json").write_text("{}", encoding="utf-8")
    (package / "config" / "tool_integration_contract.local.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("LOCAL_HARNESS_REPO", str(repo))

    contract = build_contract(
        package_root=package,
        repo_root=repo,
        store_root=tmp_path / "store",
        model_run_root=model_root,
        log_root=tmp_path / "logs",
        env_vars=["LOCAL_HARNESS_REPO", "LOCAL_SERVE_PYTHON"],
    )

    assert contract["schema"] == "harness.runtime-activation-contract/v1"
    assert contract["summary"]["ready_for_package_inspection"] is True
    assert contract["summary"]["env_vars_present"] == 1
    assert contract["secret_policy"].startswith("environment values are not recorded")


def test_runtime_contract_markdown_includes_activation_steps(tmp_path):
    contract = build_contract(
        package_root=tmp_path,
        repo_root=tmp_path,
        store_root=tmp_path / "store",
        model_run_root=tmp_path,
        log_root=tmp_path / "logs",
        env_vars=[],
    )

    markdown = render_markdown(contract)

    assert "# Runtime activation contract" in markdown
    assert "Activation steps" in markdown
    assert "Benchmarks are intentionally outside" in markdown
