import os
from pathlib import Path

import pytest

from scripts.run_tool_integration_contract import build_contract, render_markdown


def _pyproject(root: Path, text: str) -> None:
    root.mkdir(parents=True)
    (root / "pyproject.toml").write_text(text, encoding="utf-8")


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
        package_root=Path("C:/dev/public/flywheel/artifacts/exe"),
    )

    markdown = render_markdown(contract)

    assert "# Tool integration contract" in markdown
    assert "forum-route" in markdown


def test_tool_contract_uses_selected_root_pyproject_scripts(tmp_path):
    default = tmp_path / "default" / "mneme"
    override = tmp_path / "override" / "mneme"
    _pyproject(default, '[project]\nname = "mneme"\n[project.scripts]\nwrong = "wrong.cli:main"\n')
    _pyproject(override, '[project]\nname = "mneme"\n[project.scripts]\nmneme = "mneme.cli:main"\n')

    contract = build_contract(
        tools=["mneme"],
        base_root=tmp_path / "default",
        explicit_roots={"mneme": override},
        package_root=tmp_path / "package",
    )

    row = contract["tools"][0]
    assert row["entrypoints"]["cli"] == ["mneme"]
    assert row["entrypoint_metadata"]["project_scripts"]["declarations"] == [
        {"declaration": "mneme = mneme.cli:main", "name": "mneme", "target": "mneme.cli:main"}
    ]
    assert row["entrypoint_metadata"]["project_scripts"]["status"] == "declared"
    assert row["entrypoint_metadata"]["project_scripts"]["source"]["filename"] == "pyproject.toml"
    assert row["entrypoint_metadata"]["project_scripts"]["source"]["sha256"]
    assert row["entrypoint_metadata"]["cli_source"] == "pyproject_project_scripts"
    assert "wrong.cli" not in render_markdown(contract)


def test_tool_contract_reads_metadata_without_importing_script_targets(tmp_path):
    root = tmp_path / "danger"
    _pyproject(root, '[project]\nname = "danger"\n[project.scripts]\ndanger = "danger_cli:main"\n')
    (root / "danger_cli.py").write_text('raise RuntimeError("package target executed")\n', encoding="utf-8")

    contract = build_contract(
        tools=["danger"],
        base_root=tmp_path,
        explicit_roots={"danger": root},
        package_root=tmp_path / "package",
    )

    row = contract["tools"][0]
    assert row["entrypoints"]["cli"] == ["danger"]
    assert row["entrypoint_metadata"]["project_scripts"]["status"] == "declared"


def test_tool_contract_labels_absent_invalid_and_empty_metadata(tmp_path):
    absent = tmp_path / "absent"
    empty = tmp_path / "empty"
    malformed = tmp_path / "malformed"
    invalid = tmp_path / "invalid"
    absent.mkdir()
    _pyproject(empty, '[project]\nname = "mneme"\n[project.scripts]\n')
    _pyproject(malformed, "[project\nname =")
    _pyproject(invalid, '[project]\nname = "mneme"\nscripts = ["mneme"]\n')

    contract = build_contract(
        tools=["mneme", "relay", "plexus", "custom"],
        base_root=tmp_path,
        explicit_roots={
            "mneme": absent,
            "relay": empty,
            "plexus": malformed,
            "custom": invalid,
        },
        package_root=tmp_path / "package",
    )

    rows = {row["tool"]: row for row in contract["tools"]}
    assert rows["mneme"]["entrypoint_metadata"]["project_scripts"]["status"] == "absent"
    assert rows["relay"]["entrypoint_metadata"]["project_scripts"]["status"] == "empty"
    assert rows["relay"]["entrypoints"]["cli"] == []
    assert rows["plexus"]["entrypoint_metadata"]["project_scripts"]["status"] == "invalid"
    assert rows["plexus"]["entrypoint_metadata"]["project_scripts"]["source"]["sha256"]
    assert "error" not in rows["plexus"]["entrypoint_metadata"]["project_scripts"]
    assert "name =" not in str(rows["plexus"]["entrypoint_metadata"])
    assert rows["custom"]["entrypoint_metadata"]["project_scripts"]["status"] == "invalid"
    assert rows["custom"]["entrypoint_metadata"]["fallback_profile"]["status"] == "unverified_profile"


def test_tool_contract_rejects_unsupported_script_strings_without_echo(tmp_path):
    root = tmp_path / "unsafe"
    _pyproject(root, '[project]\nname = "unsafe"\n[project.scripts]\n"bad\\nname" = "safe.cli:main"\nleak = "../secret.py:main"\n')

    contract = build_contract(
        tools=["unsafe"],
        base_root=tmp_path,
        explicit_roots={"unsafe": root},
        package_root=tmp_path / "package",
    )

    row = contract["tools"][0]
    metadata_text = str(row["entrypoint_metadata"])
    assert row["entrypoints"]["cli"] == []
    assert row["entrypoint_metadata"]["project_scripts"]["status"] == "unsupported"
    assert "bad" not in metadata_text
    assert "../secret.py" not in metadata_text


def test_tool_contract_rejects_symlinked_pyproject_before_read(tmp_path):
    outside = tmp_path / "outside.toml"
    outside.write_text('[project]\nname = "outside"\n[project.scripts]\noutside = "outside.cli:main"\n', encoding="utf-8")
    root = tmp_path / "tool"
    root.mkdir()
    try:
        os.symlink(outside, root / "pyproject.toml")
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink unavailable: {exc}")

    contract = build_contract(
        tools=["tool"],
        base_root=tmp_path,
        explicit_roots={"tool": root},
        package_root=tmp_path / "package",
    )

    row = contract["tools"][0]
    assert row["entrypoints"]["cli"] == []
    assert row["entrypoint_metadata"]["project_scripts"]["status"] == "unsafe_path"
    assert "outside.cli" not in str(row["entrypoint_metadata"])


def test_tool_contract_rejects_oversized_pyproject_before_read(tmp_path):
    root = tmp_path / "large"
    padding = "# padding\n" * 30000
    _pyproject(root, '[project]\nname = "large"\n[project.scripts]\nlarge = "large.cli:main"\n' + padding)

    contract = build_contract(
        tools=["large"],
        base_root=tmp_path,
        explicit_roots={"large": root},
        package_root=tmp_path / "package",
    )

    row = contract["tools"][0]
    assert row["entrypoints"]["cli"] == []
    assert row["entrypoint_metadata"]["project_scripts"]["status"] == "too_large"
    assert "large.cli:main" not in str(row["entrypoint_metadata"])


def test_tool_contract_does_not_use_stale_relay_serve_profile(tmp_path):
    relay = tmp_path / "relay"
    relay.mkdir()

    contract = build_contract(
        tools=["relay"],
        base_root=tmp_path,
        explicit_roots={"relay": relay},
        package_root=tmp_path / "package",
    )

    row = contract["tools"][0]
    assert "python serve.py" not in row["entrypoints"]["cli"]
    assert row["entrypoint_metadata"]["cli_source"] == "unverified_profile"
def test_tool_contract_rejects_metadata_that_grows_after_path_check(tmp_path, monkeypatch):
    root = tmp_path / "growing"
    _pyproject(root, '[project.scripts]\ngrowing = "growing.cli:main"\n')
    target = root / "pyproject.toml"
    original_open = Path.open

    def grow_before_read(path, *args, **kwargs):
        if path == target and args and args[0] == "rb":
            target.write_text('[project.scripts]\ngrowing = "growing.cli:main"\n#' + "x" * 1_048_576)
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", grow_before_read)
    row = build_contract(tools=["growing"], base_root=tmp_path,
                         explicit_roots={"growing": root}, package_root=tmp_path / "package")["tools"][0]
    assert row["entrypoints"]["cli"] == []
    assert row["entrypoint_metadata"]["project_scripts"]["status"] == "too_large"


def test_tool_contract_marks_non_table_project_invalid(tmp_path):
    root = tmp_path / "malformed-project"
    _pyproject(root, 'project = "not a table"\n')
    row = build_contract(tools=["custom"], base_root=tmp_path,
                         explicit_roots={"custom": root}, package_root=tmp_path / "package")["tools"][0]
    assert row["entrypoint_metadata"]["project_scripts"]["status"] == "invalid"
    assert "not a table" not in str(row["entrypoint_metadata"])
