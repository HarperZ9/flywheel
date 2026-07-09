from pathlib import Path

from scripts.run_tool_integration_contract import build_contract, render_markdown


def test_tool_contract_marks_sidecar_and_bundled_tools(tmp_path):
    root = tmp_path / "local-model"
    (root / "harness").mkdir(parents=True)
    (root / "scripts").mkdir()
    (root / "project-docs").mkdir()
    (root / "scripts" / "run_harness_cli.py").write_text("", encoding="utf-8")
    (root / "scripts" / "local_harness_entry.py").write_text("", encoding="utf-8")
    (root / "scripts" / "build_local_harness_exes.py").write_text("", encoding="utf-8")
    (root / "scripts" / "package_local_harness_release.py").write_text("", encoding="utf-8")
    (root / "scripts" / "run_model_endpoint_profiles.py").write_text("", encoding="utf-8")
    (root / "project-docs" / "HARNESS-PACKAGING.md").write_text("", encoding="utf-8")
    (root / "harness.cmd").write_text("", encoding="utf-8")
    (root / ".gitignore").write_text("", encoding="utf-8")

    contract = build_contract(
        tools=["index", "local-model"],
        base_root=tmp_path,
        explicit_roots={
            "index": tmp_path / "missing-index",
            "local-model": root,
        },
        package_root=tmp_path / "package",
    )

    rows = {row["tool"]: row for row in contract["tools"]}
    assert rows["index"]["packaged_mode"] == "external_repo_sidecar"
    assert rows["index"]["ship_status"] == "wired_root_missing"
    assert rows["local-model"]["packaged_mode"] == "bundled_core_plus_external_model_runtime"
    assert rows["local-model"]["ship_status"] == "wired_root_present"
    assert contract["summary"]["bundled_core_tools"] == 1
    assert contract["summary"]["sidecar_tools"] == 1


def test_tool_contract_markdown_lists_harness_commands(tmp_path):
    contract = build_contract(
        tools=["forum"],
        base_root=tmp_path,
        explicit_roots={"forum": tmp_path / "forum"},
        package_root=Path("C:/dev/local-model/artifacts/exe"),
    )

    markdown = render_markdown(contract)

    assert "# Tool integration contract" in markdown
    assert "forum-route" in markdown
