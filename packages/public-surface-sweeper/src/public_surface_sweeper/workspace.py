from __future__ import annotations

import os
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .sweeper import Finding, scan_delivery_surface, summarize_findings

WORKSPACE_SKIP_DIRS = {
    ".git",
    ".hg",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".superpowers",
    ".telos",
    ".tox",
    ".venv",
    ".vscode",
    "__pycache__",
    "_deps",
    "build",
    "coverage",
    "dist",
    "external",
    "node_modules",
    "target",
    "third_party",
    "vendor",
    "vcpkg",
}
PUBLIC_DELIVERY_RULES = {
    "em-dash",
    "public-changelog",
    "public-funding",
    "readme-public-delivery",
    "readme-visual-asset",
    "required-file",
}
DEVELOPER_DELIVERY_RULES = {
    "developer-agent-instructions",
    "developer-ci-workflow",
    "developer-usage-doc",
    "readme-developer-delivery",
}
SECRET_RULE_PREFIXES = (
    "aws-access-key",
    "github-token",
    "openai-key",
    "private-key",
    "secret-assignment",
    "slack-token",
)


@dataclass(frozen=True)
class _GitMetadata:
    repo: Path
    config_paths: tuple[Path, ...]
    reason: str | None = None

    @property
    def is_readable(self) -> bool:
        return self.reason is None


def discover_forward_facing_repos(roots: Iterable[Path]) -> list[Path]:
    root_list = [Path(root).resolve() for root in roots]
    repos, _ = _discover_workspace(root_list)
    return repos


def build_delivery_matrix(roots: Iterable[Path]) -> dict[str, Any]:
    root_list = [Path(root).resolve() for root in roots]
    discovered_repos, coverage = _discover_workspace(root_list)
    repositories = []
    counts = Counter({"MATCH": 0, "DRIFT": 0, "UNVERIFIABLE": 0})
    for repo in discovered_repos:
        item = _repo_delivery_record(repo, root_list)
        repositories.append(item)
        counts[item["status"]] += 1
    repository_count = len(repositories)
    workspace_status = _workspace_status(repository_count, counts, coverage)
    coverage["github_repository_count"] = repository_count
    coverage["empty_reason"] = _empty_reason(repository_count, coverage)
    return {
        "schema": "public-surface-sweeper.delivery-matrix/v1",
        "repository_count": repository_count,
        "counts": dict(counts),
        "workspace_status": workspace_status,
        "coverage": coverage,
        "privacy_boundary": {
            "absolute_paths_included": False,
            "raw_secret_values_included": False,
            "network_calls_performed": False,
            "filesystem_writes_performed": False,
        },
        "repositories": repositories,
    }


def format_delivery_matrix(matrix: dict[str, Any]) -> str:
    counts = matrix["counts"]
    coverage = matrix.get("coverage", {})
    lines = [
        "workspace_delivery_matrix:",
        f"status: {matrix.get('workspace_status', 'MATCH')}",
        f"repositories: {matrix['repository_count']}",
        (
            "counts: "
            f"MATCH={counts['MATCH']} "
            f"DRIFT={counts['DRIFT']} "
            f"UNVERIFIABLE={counts['UNVERIFIABLE']}"
        ),
        (
            "coverage: "
            f"git={coverage.get('git_repository_count', matrix['repository_count'])} "
            f"github={coverage.get('github_repository_count', matrix['repository_count'])} "
            f"unknown={coverage.get('unknown_repository_count', 0)}"
        ),
        "items:",
    ]
    empty_reason = coverage.get("empty_reason")
    if not matrix["repositories"]:
        detail = f"- none ({empty_reason})" if empty_reason else "- none"
        return "\n".join(lines + [detail, *_format_diagnostic_lines(coverage)])
    for repo in matrix["repositories"]:
        lines.extend(_format_repo_lines(repo))
    lines.extend(_format_diagnostic_lines(coverage))
    return "\n".join(lines)


def github_remote_slug(repo: Path) -> str | None:
    for url in _remote_urls(repo):
        slug = _github_slug_from_url(url)
        if slug is not None:
            return slug
    return None


def _discover_workspace(root_list: list[Path]) -> tuple[list[Path], dict[str, Any]]:
    repos_by_remote: dict[str, Path] = {}
    git_repository_count = 0
    diagnostics: list[dict[str, str]] = []
    for root in root_list:
        for metadata in _iter_git_metadata(root):
            if not metadata.is_readable:
                diagnostics.append(
                    {
                        "path": _display_path(metadata.repo, root_list),
                        "status": "UNVERIFIABLE",
                        "reason": metadata.reason or "git metadata not readable",
                    }
                )
                continue
            git_repository_count += 1
            slug = _github_slug_from_config_paths(metadata.config_paths)
            if slug is None:
                continue
            current = repos_by_remote.get(slug)
            if current is None or _repo_rank(metadata.repo) < _repo_rank(current):
                repos_by_remote[slug] = metadata.repo
    repositories = sorted(repos_by_remote.values(), key=lambda path: path.name.lower())
    return repositories, {
        "root_count": len(root_list),
        "git_repository_count": git_repository_count,
        "github_repository_count": len(repositories),
        "unknown_repository_count": len(diagnostics),
        "empty_reason": None,
        "diagnostics": diagnostics,
    }


def _workspace_status(
    repository_count: int, counts: Counter[str], coverage: dict[str, Any]
) -> str:
    if coverage["unknown_repository_count"]:
        return "UNVERIFIABLE"
    if repository_count == 0:
        return "EMPTY"
    if counts["UNVERIFIABLE"]:
        return "UNVERIFIABLE"
    if counts["DRIFT"]:
        return "DRIFT"
    return "MATCH"


def _empty_reason(repository_count: int, coverage: dict[str, Any]) -> str | None:
    if repository_count:
        return None
    if coverage["unknown_repository_count"] and not coverage["git_repository_count"]:
        return "no_readable_git_metadata"
    if coverage["git_repository_count"]:
        return "no_github_repositories"
    return "no_git_repositories"


def _iter_git_repos(root: Path) -> Iterable[Path]:
    for metadata in _iter_git_metadata(root):
        if metadata.is_readable:
            yield metadata.repo


def _iter_git_metadata(root: Path) -> Iterable[_GitMetadata]:
    if not root.exists():
        return
    for current, dirnames, _ in os.walk(root):
        dirnames[:] = [name for name in dirnames if name not in WORKSPACE_SKIP_DIRS]
        current_path = Path(current)
        metadata = _read_git_metadata(current_path)
        if metadata is not None:
            yield metadata
            if metadata.is_readable and _github_slug_from_config_paths(metadata.config_paths):
                dirnames[:] = []


def _repo_delivery_record(repo: Path, roots: list[Path]) -> dict[str, Any]:
    try:
        findings = scan_delivery_surface(repo)
    except OSError as exc:
        return _unverifiable_record(repo, roots, str(exc))
    summary = summarize_findings(findings)
    public_verdict = _rule_verdict(findings, PUBLIC_DELIVERY_RULES)
    developer_verdict = _rule_verdict(findings, DEVELOPER_DELIVERY_RULES)
    boundary_verdict = _boundary_verdict(findings)
    status = _overall_status(public_verdict, developer_verdict, boundary_verdict)
    return {
        "name": repo.name,
        "path": _display_path(repo, roots),
        "remote": github_remote_slug(repo),
        "status": status,
        "score": summary.score,
        "public_delivery": public_verdict,
        "developer_delivery": developer_verdict,
        "boundary": boundary_verdict,
        "findings": {
            "total": summary.total_findings,
            "errors": summary.errors,
            "warnings": summary.warnings,
            "rules": dict(Counter(item.rule for item in findings)),
            "action_items": summary.action_items,
        },
    }


def _unverifiable_record(repo: Path, roots: list[Path], reason: str) -> dict[str, Any]:
    return {
        "name": repo.name,
        "path": _display_path(repo, roots),
        "remote": github_remote_slug(repo),
        "status": "UNVERIFIABLE",
        "score": 0,
        "public_delivery": "UNVERIFIABLE",
        "developer_delivery": "UNVERIFIABLE",
        "boundary": "UNVERIFIABLE",
        "findings": {
            "total": 1,
            "errors": 1,
            "warnings": 0,
            "rules": {"scan-error": 1},
            "action_items": [f"scan-error: {reason}"],
        },
    }


def _rule_verdict(findings: list[Finding], rules: set[str]) -> str:
    return "DRIFT" if any(item.rule in rules for item in findings) else "MATCH"


def _boundary_verdict(findings: list[Finding]) -> str:
    for item in findings:
        if item.rule in SECRET_RULE_PREFIXES:
            return "DRIFT"
    return "MATCH"


def _overall_status(*verdicts: str) -> str:
    if "UNVERIFIABLE" in verdicts:
        return "UNVERIFIABLE"
    if "DRIFT" in verdicts:
        return "DRIFT"
    return "MATCH"


def _display_path(repo: Path, roots: list[Path]) -> str:
    resolved = repo.resolve()
    for root in roots:
        try:
            rel = resolved.relative_to(root)
        except ValueError:
            continue
        return rel.as_posix() or repo.name
    return repo.name


def _remote_urls(repo: Path) -> list[str]:
    metadata = _read_git_metadata(repo)
    if metadata is None or not metadata.is_readable:
        return []
    return _remote_urls_from_config_paths(metadata.config_paths)


def _read_git_metadata(repo: Path) -> _GitMetadata | None:
    marker = repo / ".git"
    if marker.is_symlink():
        reason = (
            ".git directory symlink not supported"
            if marker.is_dir()
            else ".git file symlink not supported"
        )
        return _GitMetadata(repo=repo, config_paths=(), reason=reason)
    if marker.is_dir():
        config = marker / "config"
        if config.is_file():
            return _GitMetadata(repo=repo, config_paths=(config,))
        return _GitMetadata(repo=repo, config_paths=(), reason="git config not found")
    if marker.is_file():
        return _read_gitfile_metadata(repo, marker)
    return None


def _read_gitfile_metadata(repo: Path, marker: Path) -> _GitMetadata:
    try:
        text = marker.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return _GitMetadata(repo=repo, config_paths=(), reason=".git file not readable")
    first_line = text.splitlines()[0].strip() if text.splitlines() else ""
    match = re.match(r"^gitdir:\s*(?P<gitdir>.+?)\s*$", first_line, re.IGNORECASE)
    if match is None:
        return _GitMetadata(repo=repo, config_paths=(), reason="unsupported .git file")
    raw_gitdir = match.group("gitdir")
    if _has_control_characters(raw_gitdir):
        return _GitMetadata(repo=repo, config_paths=(), reason="gitdir target not found")
    git_dir = Path(raw_gitdir)
    if not git_dir.is_absolute():
        git_dir = marker.parent / git_dir
    try:
        git_dir = git_dir.resolve()
    except (OSError, ValueError):
        return _GitMetadata(repo=repo, config_paths=(), reason="gitdir target not found")
    if not git_dir.is_dir():
        return _GitMetadata(repo=repo, config_paths=(), reason="gitdir target not found")
    if git_dir.is_symlink():
        return _GitMetadata(repo=repo, config_paths=(), reason="gitdir target symlink not supported")
    validation_error = _validate_linked_git_dir(marker, git_dir)
    if validation_error is not None:
        return _GitMetadata(repo=repo, config_paths=(), reason=validation_error)
    config_paths = _git_config_paths(git_dir)
    if not config_paths:
        return _GitMetadata(repo=repo, config_paths=(), reason="git config not found")
    return _GitMetadata(repo=repo, config_paths=config_paths)


def _validate_linked_git_dir(marker: Path, git_dir: Path) -> str | None:
    backpointer = git_dir / "gitdir"
    try:
        backpointer_lines = backpointer.read_text(
            encoding="utf-8", errors="replace"
        ).splitlines()
    except OSError:
        return "gitdir backpointer not found"
    if not backpointer_lines or not backpointer_lines[0].strip():
        return "gitdir backpointer not found"
    pointed_marker = _resolve_git_metadata_path(
        backpointer_lines[0].strip(), git_dir
    )
    if pointed_marker is None or pointed_marker != marker.resolve():
        return "gitdir backpointer mismatch"
    common_dir = _common_git_dir(git_dir)
    if common_dir is None or not common_dir.is_dir():
        return "git commondir not found"
    try:
        expected_parent = (common_dir / "worktrees").resolve()
        actual_parent = git_dir.parent.resolve()
    except (OSError, ValueError):
        return "gitdir is outside common worktrees directory"
    if actual_parent != expected_parent:
        return "gitdir is outside common worktrees directory"
    return None


def _resolve_git_metadata_path(raw: str, base: Path) -> Path | None:
    if _has_control_characters(raw):
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = base / path
    try:
        return path.resolve()
    except (OSError, ValueError):
        return None


def _git_config_paths(git_dir: Path) -> tuple[Path, ...]:
    paths: list[Path] = []
    for name in ("config", "config.worktree"):
        candidate = git_dir / name
        if candidate.is_file():
            paths.append(candidate)
    common_dir = _common_git_dir(git_dir)
    if common_dir is not None:
        common_config = common_dir / "config"
        if common_config.is_file() and common_config not in paths:
            paths.append(common_config)
    return tuple(paths)


def _common_git_dir(git_dir: Path) -> Path | None:
    commondir = git_dir / "commondir"
    try:
        text = commondir.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    if not text:
        return None
    common_text = text[0].strip()
    if not common_text:
        return None
    if _has_control_characters(common_text):
        return None
    common = Path(common_text)
    if not common.is_absolute():
        common = git_dir / common
    try:
        return common.resolve()
    except (OSError, ValueError):
        return None


def _has_control_characters(value: str) -> bool:
    return any(ord(char) < 32 for char in value)


def _remote_urls_from_config_paths(config_paths: Iterable[Path]) -> list[str]:
    urls: list[str] = []
    for config in config_paths:
        urls.extend(_remote_urls_from_config(config))
    return urls


def _remote_urls_from_config(config: Path) -> list[str]:
    try:
        text = config.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return [
        match.group("url").strip()
        for match in re.finditer(r"^\s*url\s*=\s*(?P<url>\S+)\s*$", text, re.MULTILINE)
    ]


def _github_slug_from_config_paths(config_paths: Iterable[Path]) -> str | None:
    for url in _remote_urls_from_config_paths(config_paths):
        slug = _github_slug_from_url(url)
        if slug is not None:
            return slug
    return None


def _github_slug_from_url(url: str) -> str | None:
    patterns = (
        r"^git@github\.com:(?P<slug>[^/]+/[^/]+?)(?:\.git)?$",
        r"^https://github\.com/(?P<slug>[^/]+/[^/]+?)(?:\.git)?/?$",
        r"^ssh://git@github\.com/(?P<slug>[^/]+/[^/]+?)(?:\.git)?/?$",
    )
    for pattern in patterns:
        match = re.match(pattern, url)
        if match:
            return match.group("slug")
    return None


def _repo_rank(path: Path) -> tuple[int, int, str]:
    parts = {part.lower() for part in path.parts}
    mirror_penalty = 1 if "pubscan" in parts else 0
    return (mirror_penalty, len(path.parts), path.as_posix().lower())


def _format_repo_lines(repo: dict[str, Any]) -> list[str]:
    lines = [
        (
            f"- {repo['name']} ({repo['remote']}): {repo['status']} "
            f"score={repo['score']} public={repo['public_delivery']} "
            f"developer={repo['developer_delivery']}"
        )
    ]
    for item in repo["findings"]["action_items"][:3]:
        lines.append(f"  action: {item}")
    return lines


def _format_diagnostic_lines(coverage: dict[str, Any]) -> list[str]:
    diagnostics = coverage.get("diagnostics", [])
    if not diagnostics:
        return []
    lines = ["diagnostics:"]
    for item in diagnostics:
        lines.append(f"- {item['path']}: {item['status']} {item['reason']}")
    return lines
