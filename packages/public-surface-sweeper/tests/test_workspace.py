from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from public_surface_sweeper.workspace import (
    build_delivery_matrix,
    discover_forward_facing_repos,
)


def _write_git_config(repo: Path, remote: str) -> None:
    git_dir = repo / ".git"
    git_dir.mkdir(parents=True)
    (git_dir / "config").write_text(
        "[core]\n"
        "\trepositoryformatversion = 0\n"
        "[remote \"origin\"]\n"
        f"\turl = {remote}\n",
        encoding="utf-8",
    )


def _write_required_files(
    repo: Path, readme: str, include_delivery_contract: bool = True
) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    brand_dir = repo / "docs" / "brand"
    brand_dir.mkdir(parents=True)
    (brand_dir / "demo-hero.png").write_bytes(b"fake image")
    (repo / "README.md").write_text(readme, encoding="utf-8")
    for name in ("LICENSE", "AUTHORS.md", "CONTRIBUTING.md"):
        (repo / name).write_text("ok\n", encoding="utf-8")
    if include_delivery_contract:
        (repo / "AGENTS.md").write_text("# Agent Instructions\n\nRun tests first.\n", encoding="utf-8")
        (repo / "USAGE.md").write_text("# Usage\n\nInstall and run the CLI.\n", encoding="utf-8")
        (repo / "CHANGELOG.md").write_text("# Changelog\n\n## Unreleased\n\n- Current.\n", encoding="utf-8")
        workflow_dir = repo / ".github" / "workflows"
        workflow_dir.mkdir(parents=True)
        (repo / ".github" / "FUNDING.yml").write_text("github: HarperZ9\n", encoding="utf-8")
        (workflow_dir / "ci.yml").write_text(
            "name: CI\n\non: [push, pull_request]\n\njobs:\n"
            "  test:\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - uses: actions/checkout@v5\n"
            "      - run: python -m pytest\n",
            encoding="utf-8",
        )


def _complete_readme() -> str:
    return (
        "# Demo\n\n"
        "![Demo hero](docs/brand/demo-hero.png)\n\n"
        "## Why it matters\n\n"
        "This explains the public value.\n\n"
        "## Try it\n\n"
        "```bash\npython -m demo\n```\n\n"
        "## For developers\n\n"
        "```bash\npython -m pytest\n```\n"
    )


def _run_git(cwd: Path, *args: str) -> None:
    try:
        subprocess.run(
            ["git", *args],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        pytest.skip("git executable is required for linked-worktree coverage")


def _run_workspace_cli(root: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    local_src = str(Path(__file__).parents[1] / "src")
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = local_src + os.pathsep + existing if existing else local_src
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "public_surface_sweeper",
            str(root),
            "--workspace",
            "--json",
        ],
        check=False,
        capture_output=True,
        env=env,
        text=True,
    )


def test_discovers_only_github_facing_repositories(tmp_path: Path) -> None:
    public_repo = tmp_path / "public-tool"
    local_repo = tmp_path / "local-tool"
    nested_repo = tmp_path / "node_modules" / "ignored-tool"
    _write_git_config(public_repo, "git@github.com:HarperZ9/public-tool.git")
    _write_git_config(local_repo, "file:///tmp/local-tool")
    _write_git_config(nested_repo, "https://github.com/HarperZ9/ignored-tool.git")

    repos = discover_forward_facing_repos([tmp_path])

    assert [repo.name for repo in repos] == ["public-tool"]


def test_discovers_github_remote_from_linked_worktree_gitfile(tmp_path: Path) -> None:
    source = tmp_path / "source"
    workspace = tmp_path / "workspace"
    linked_repo = workspace / "linked-tool"
    source.mkdir()
    _run_git(source, "init")
    _run_git(source, "checkout", "-b", "main")
    _write_required_files(source, _complete_readme())
    _run_git(source, "add", ".")
    _run_git(
        source,
        "-c",
        "user.name=Public Surface Tests",
        "-c",
        "user.email=tests@example.invalid",
        "commit",
        "-m",
        "initial fixture",
    )
    _run_git(
        source,
        "remote",
        "add",
        "origin",
        "https://github.com/HarperZ9/linked-tool.git",
    )
    _run_git(source, "worktree", "add", "--detach", str(linked_repo), "HEAD")

    repos = discover_forward_facing_repos([workspace])
    matrix = build_delivery_matrix([workspace])

    assert (linked_repo / ".git").is_file()
    assert repos == [linked_repo]
    assert matrix["workspace_status"] == "MATCH"
    assert matrix["coverage"]["git_repository_count"] == 1
    assert matrix["coverage"]["github_repository_count"] == 1
    assert matrix["repositories"][0]["remote"] == "HarperZ9/linked-tool"


def test_discovery_deduplicates_multiple_clones_of_same_remote(tmp_path: Path) -> None:
    canonical_repo = tmp_path / "ready-tool"
    mirror_repo = tmp_path / "pubscan" / "ready-tool"
    _write_git_config(canonical_repo, "https://github.com/HarperZ9/ready-tool.git")
    _write_git_config(mirror_repo, "https://github.com/HarperZ9/ready-tool.git")

    repos = discover_forward_facing_repos([tmp_path])

    assert repos == [canonical_repo]


def test_discovery_continues_through_local_wrapper_repositories(tmp_path: Path) -> None:
    wrapper = tmp_path / "wrapper"
    nested_repo = wrapper / "nested-tool"
    _write_git_config(wrapper, "file:///tmp/wrapper")
    _write_git_config(nested_repo, "https://github.com/HarperZ9/nested-tool.git")

    repos = discover_forward_facing_repos([wrapper])

    assert repos == [nested_repo]


def test_delivery_matrix_reports_empty_non_git_workspace(tmp_path: Path) -> None:
    matrix = build_delivery_matrix([tmp_path])

    assert matrix["repository_count"] == 0
    assert matrix["workspace_status"] == "EMPTY"
    assert matrix["coverage"]["empty_reason"] == "no_git_repositories"
    assert matrix["coverage"]["git_repository_count"] == 0
    assert matrix["coverage"]["github_repository_count"] == 0
    assert matrix["coverage"]["unknown_repository_count"] == 0
    assert str(tmp_path) not in json.dumps(matrix)


def test_delivery_matrix_reports_no_github_repositories(tmp_path: Path) -> None:
    repo = tmp_path / "local-tool"
    _write_git_config(repo, "file:///tmp/local-tool")

    matrix = build_delivery_matrix([tmp_path])

    assert matrix["repository_count"] == 0
    assert matrix["workspace_status"] == "EMPTY"
    assert matrix["coverage"]["empty_reason"] == "no_github_repositories"
    assert matrix["coverage"]["git_repository_count"] == 1
    assert matrix["coverage"]["github_repository_count"] == 0
    assert matrix["coverage"]["unknown_repository_count"] == 0


def test_delivery_matrix_reports_invalid_gitfile_marker(tmp_path: Path) -> None:
    repo = tmp_path / "broken-worktree"
    repo.mkdir()
    (repo / ".git").write_text("gitdir: missing-git-dir\n", encoding="utf-8")

    matrix = build_delivery_matrix([tmp_path])

    assert matrix["repository_count"] == 0
    assert matrix["workspace_status"] == "UNVERIFIABLE"
    assert matrix["coverage"]["empty_reason"] == "no_readable_git_metadata"
    assert matrix["coverage"]["git_repository_count"] == 0
    assert matrix["coverage"]["github_repository_count"] == 0
    assert matrix["coverage"]["unknown_repository_count"] == 1
    assert matrix["coverage"]["diagnostics"] == [
        {
            "path": "broken-worktree",
            "status": "UNVERIFIABLE",
            "reason": "gitdir target not found",
        }
    ]
    assert str(tmp_path) not in json.dumps(matrix)


def test_delivery_matrix_rejects_external_gitdir_without_backpointer(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    repo = workspace / "forged-worktree"
    external_git_dir = tmp_path / "external-git-dir"
    repo.mkdir(parents=True)
    external_git_dir.mkdir()
    (external_git_dir / "config").write_text(
        '[remote "origin"]\n'
        "\turl = https://github.com/HarperZ9/forged-worktree.git\n",
        encoding="utf-8",
    )
    (repo / ".git").write_text(f"gitdir: {external_git_dir}\n", encoding="utf-8")

    matrix = build_delivery_matrix([workspace])

    assert matrix["repository_count"] == 0
    assert matrix["workspace_status"] == "UNVERIFIABLE"
    assert matrix["coverage"]["diagnostics"] == [
        {
            "path": "forged-worktree",
            "status": "UNVERIFIABLE",
            "reason": "gitdir backpointer not found",
        }
    ]
    assert "HarperZ9/forged-worktree" not in json.dumps(matrix)
    assert str(external_git_dir) not in json.dumps(matrix)


def test_delivery_matrix_rejects_external_gitdir_with_invalid_commondir(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    repo = workspace / "forged-backpointer"
    external_git_dir = tmp_path / "external-git-dir"
    repo.mkdir(parents=True)
    external_git_dir.mkdir()
    (external_git_dir / "gitdir").write_text(str(repo / ".git"), encoding="utf-8")
    (external_git_dir / "commondir").write_text(".\n", encoding="utf-8")
    (external_git_dir / "config").write_text(
        '[remote "origin"]\n'
        "\turl = https://github.com/HarperZ9/forged-backpointer.git\n",
        encoding="utf-8",
    )
    (repo / ".git").write_text(f"gitdir: {external_git_dir}\n", encoding="utf-8")

    matrix = build_delivery_matrix([workspace])

    assert matrix["repository_count"] == 0
    assert matrix["workspace_status"] == "UNVERIFIABLE"
    assert matrix["coverage"]["diagnostics"] == [
        {
            "path": "forged-backpointer",
            "status": "UNVERIFIABLE",
            "reason": "gitdir is outside common worktrees directory",
        }
    ]
    assert "HarperZ9/forged-backpointer" not in json.dumps(matrix)


def test_delivery_matrix_rejects_git_directory_symlink(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    repo = workspace / "symlinked-git"
    external_git_dir = tmp_path / "external-git-dir"
    repo.mkdir(parents=True)
    external_git_dir.mkdir()
    (external_git_dir / "config").write_text(
        '[remote "origin"]\n'
        "\turl = https://github.com/HarperZ9/symlinked-git.git\n",
        encoding="utf-8",
    )
    try:
        (repo / ".git").symlink_to(external_git_dir, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"directory symlink unavailable: {exc}")

    matrix = build_delivery_matrix([workspace])

    assert matrix["repository_count"] == 0
    assert matrix["workspace_status"] == "UNVERIFIABLE"
    assert matrix["coverage"]["diagnostics"] == [
        {
            "path": "symlinked-git",
            "status": "UNVERIFIABLE",
            "reason": ".git directory symlink not supported",
        }
    ]
    assert "HarperZ9/symlinked-git" not in json.dumps(matrix)


def test_delivery_matrix_splits_public_and_developer_verdicts(tmp_path: Path) -> None:
    ready_repo = tmp_path / "ready-tool"
    drift_repo = tmp_path / "drift-tool"
    _write_git_config(ready_repo, "https://github.com/HarperZ9/ready-tool.git")
    _write_required_files(ready_repo, _complete_readme())
    _write_git_config(drift_repo, "https://github.com/HarperZ9/drift-tool.git")
    _write_required_files(drift_repo, "# Drift\n\nA useful tool.\n")

    matrix = build_delivery_matrix([tmp_path])

    assert matrix["schema"] == "public-surface-sweeper.delivery-matrix/v1"
    assert matrix["privacy_boundary"]["absolute_paths_included"] is False
    by_name = {repo["name"]: repo for repo in matrix["repositories"]}
    assert by_name["ready-tool"]["public_delivery"] == "MATCH"
    assert by_name["ready-tool"]["developer_delivery"] == "MATCH"
    assert by_name["drift-tool"]["public_delivery"] == "DRIFT"
    assert by_name["drift-tool"]["developer_delivery"] == "DRIFT"
    assert by_name["drift-tool"]["findings"]["warnings"] == 3
    assert not any(str(tmp_path) in json.dumps(repo) for repo in matrix["repositories"])


def test_delivery_matrix_classifies_contract_gaps_by_audience(tmp_path: Path) -> None:
    repo = tmp_path / "contract-gap"
    _write_git_config(repo, "https://github.com/HarperZ9/contract-gap.git")
    _write_required_files(repo, _complete_readme(), include_delivery_contract=False)

    matrix = build_delivery_matrix([tmp_path])

    item = matrix["repositories"][0]
    assert item["status"] == "DRIFT"
    assert item["public_delivery"] == "DRIFT"
    assert item["developer_delivery"] == "DRIFT"
    assert item["boundary"] == "MATCH"
    assert item["findings"]["rules"] == {
        "developer-agent-instructions": 1,
        "developer-ci-workflow": 1,
        "developer-usage-doc": 1,
        "public-changelog": 1,
        "public-funding": 1,
    }


def test_cli_emits_workspace_matrix_json(tmp_path: Path) -> None:
    repo = tmp_path / "ready-tool"
    _write_git_config(repo, "https://github.com/HarperZ9/ready-tool.git")
    _write_required_files(repo, _complete_readme())

    result = _run_workspace_cli(tmp_path)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["counts"] == {"MATCH": 1, "DRIFT": 0, "UNVERIFIABLE": 0}
    assert payload["repositories"][0]["remote"] == "HarperZ9/ready-tool"


@pytest.mark.parametrize(
    ("repo_name", "reason"),
    [
        ("nul-gitdir-tool", "gitdir target not found"),
        ("nul-backpointer-tool", "gitdir backpointer mismatch"),
        ("nul-commondir-tool", "git commondir not found"),
    ],
)
def test_cli_reports_control_character_git_metadata_as_unverifiable_json(
    tmp_path: Path, repo_name: str, reason: str
) -> None:
    workspace = tmp_path / "workspace"
    repo = workspace / repo_name
    repo.mkdir(parents=True)

    if repo_name == "nul-gitdir-tool":
        (repo / ".git").write_text("gitdir: bad\x00gitdir\n", encoding="utf-8")
    else:
        git_dir = tmp_path / "common" / "worktrees" / repo_name
        git_dir.mkdir(parents=True)
        (repo / ".git").write_text(f"gitdir: {git_dir}\n", encoding="utf-8")
        if repo_name == "nul-backpointer-tool":
            (git_dir / "gitdir").write_text("bad\x00marker\n", encoding="utf-8")
            (git_dir / "commondir").write_text("..\\..\n", encoding="utf-8")
        else:
            (git_dir / "gitdir").write_text(str(repo / ".git"), encoding="utf-8")
            (git_dir / "commondir").write_text("bad\x00commondir\n", encoding="utf-8")

    result = _run_workspace_cli(workspace)

    assert result.returncode == 1, result.stderr
    assert result.stderr == ""
    payload = json.loads(result.stdout)
    assert payload["repository_count"] == 0
    assert payload["workspace_status"] == "UNVERIFIABLE"
    assert payload["coverage"]["empty_reason"] == "no_readable_git_metadata"
    assert payload["coverage"]["unknown_repository_count"] == 1
    assert payload["coverage"]["diagnostics"] == [
        {"path": repo_name, "status": "UNVERIFIABLE", "reason": reason}
    ]
    assert "\x00" not in result.stdout
    assert "bad" not in result.stdout
    assert str(tmp_path) not in result.stdout


def test_cli_fails_empty_workspace_with_json_reason(tmp_path: Path) -> None:
    result = _run_workspace_cli(tmp_path)

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["workspace_status"] == "EMPTY"
    assert payload["coverage"]["empty_reason"] == "no_git_repositories"


def test_cli_fails_workspace_with_no_github_remotes(tmp_path: Path) -> None:
    repo = tmp_path / "local-tool"
    _write_git_config(repo, "file:///tmp/local-tool")

    result = _run_workspace_cli(tmp_path)

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["workspace_status"] == "EMPTY"
    assert payload["coverage"]["empty_reason"] == "no_github_repositories"
