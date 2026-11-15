from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

FindingFactory = Callable[..., Any]

CHANGELOG_FILES = ("CHANGELOG.md", "RELEASE_NOTES.md", "RELEASE.md")
FUNDING_FILES = (
    ".github/FUNDING.yml",
    ".github/FUNDING.yaml",
    "FUNDING.yml",
    "FUNDING.yaml",
)
AGENT_INSTRUCTION_FILES = ("AGENTS.md", "CLAUDE.md")
USAGE_FILES = ("USAGE.md", "docs/USAGE.md", "docs/usage.md")
WORKFLOW_GLOBS = ("*.yml", "*.yaml")


def delivery_contract_findings(root: Path, finding: FindingFactory) -> list[Any]:
    return [
        *_public_contract_findings(root, finding),
        *_developer_contract_findings(root, finding),
    ]


def _public_contract_findings(root: Path, finding: FindingFactory) -> list[Any]:
    findings: list[Any] = []
    if not _has_any_file(root, CHANGELOG_FILES):
        findings.append(
            finding(
                path="CHANGELOG.md",
                line=0,
                rule="public-changelog",
                severity="warning",
                message="add changelog or release notes so public status is inspectable",
            )
        )
    if not _has_any_file(root, FUNDING_FILES):
        findings.append(
            finding(
                path=".github/FUNDING.yml",
                line=0,
                rule="public-funding",
                severity="warning",
                message="add GitHub funding metadata for the public repository surface",
            )
        )
    return findings


def _developer_contract_findings(root: Path, finding: FindingFactory) -> list[Any]:
    findings: list[Any] = []
    if not _has_any_file(root, AGENT_INSTRUCTION_FILES):
        findings.append(
            finding(
                path="AGENTS.md",
                line=0,
                rule="developer-agent-instructions",
                severity="warning",
                message="add agent/developer instructions for repeatable handoffs",
            )
        )
    if not _has_any_file(root, USAGE_FILES):
        findings.append(
            finding(
                path="USAGE.md",
                line=0,
                rule="developer-usage-doc",
                severity="warning",
                message="add standalone usage docs with install, run, and verify steps",
            )
        )
    if not _has_workflow(root):
        findings.append(
            finding(
                path=".github/workflows",
                line=0,
                rule="developer-ci-workflow",
                severity="warning",
                message="add CI or workflow evidence for developer verification",
            )
        )
    return findings


def _has_any_file(root: Path, candidates: tuple[str, ...]) -> bool:
    return any((root / candidate).is_file() for candidate in candidates)


def _has_workflow(root: Path) -> bool:
    workflow_dir = root / ".github" / "workflows"
    if not workflow_dir.is_dir():
        return False
    return any(path.is_file() for pattern in WORKFLOW_GLOBS for path in workflow_dir.glob(pattern))
