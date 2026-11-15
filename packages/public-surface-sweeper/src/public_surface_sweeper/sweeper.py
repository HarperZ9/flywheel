from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .delivery_contract import delivery_contract_findings
from .file_io import read_text_file
from .models import SEVERITY_ORDER, Finding, SweepSummary
from .readme_delivery import readme_delivery_findings
from .summary import (
    format_summary,
    format_text,
    proof_surface_packet,
    summarize_findings,
)
from .text_hygiene import text_findings

REQUIRED_FILES = ("README.md", "LICENSE", "AUTHORS.md", "CONTRIBUTING.md")
DELIVERY_SURFACE_FILES = (
    ".dockerignore",
    ".env.example",
    ".github/FUNDING.yml",
    ".github/FUNDING.yaml",
    ".gitignore",
    "AGENTS.md",
    "AUTHORS.md",
    "CHANGELOG.md",
    "CLAUDE.md",
    "CODE_OF_CONDUCT.md",
    "CONTRIBUTING.md",
    "Cargo.toml",
    "LICENSE",
    "MANIFEST.in",
    "README.md",
    "RELEASE.md",
    "RELEASE_NOTES.md",
    "SECURITY.md",
    "SUPPORT.md",
    "USAGE.md",
    "package.json",
    "pyproject.toml",
    "setup.py",
)
DELIVERY_SURFACE_DIRS = (".github/workflows", "docs")
DELIVERY_SURFACE_SUFFIXES = (".json", ".md", ".toml", ".txt", ".yaml", ".yml")
SKIP_DIRS = {
    ".git",
    ".Codex",
    ".claude",
    ".codex",
    ".hg",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".superpowers",
    ".telos",
    ".tox",
    ".venv",
    ".vscode",
    ".warden-safe-cache",
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

__all__ = [
    "SEVERITY_ORDER",
    "Finding",
    "SweepSummary",
    "format_summary",
    "format_text",
    "proof_surface_packet",
    "scan",
    "scan_delivery_surface",
    "summarize_findings",
]


def _iter_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.is_file():
            yield path


def _required_file_findings(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for name in REQUIRED_FILES:
        if not (root / name).is_file():
            findings.append(
                Finding(
                    path=name,
                    line=0,
                    rule="required-file",
                    severity="error",
                    message=f"missing required file: {name}",
                )
            )
    return findings


def _iter_delivery_surface_files(root: Path) -> Iterable[Path]:
    seen: set[Path] = set()
    for relative in DELIVERY_SURFACE_FILES:
        path = root / relative
        if path.is_file():
            seen.add(path.resolve())
            yield path
    for relative in DELIVERY_SURFACE_DIRS:
        directory = root / relative
        if not directory.is_dir():
            continue
        for path in directory.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in DELIVERY_SURFACE_SUFFIXES:
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            yield path


def _base_delivery_findings(root: Path) -> list[Finding]:
    findings = _required_file_findings(root)
    findings.extend(readme_delivery_findings(root))
    findings.extend(delivery_contract_findings(root, Finding))
    return findings


def scan_delivery_surface(root: Path) -> list[Finding]:
    root = root.resolve()
    findings = _base_delivery_findings(root)
    for path in _iter_delivery_surface_files(root):
        text = read_text_file(path)
        if text is not None:
            findings.extend(text_findings(root, path, text))
    return sorted(findings, key=lambda item: (item.severity, item.path, item.line, item.rule))


def scan(root: Path) -> list[Finding]:
    root = root.resolve()
    findings = _base_delivery_findings(root)
    for path in _iter_files(root):
        text = read_text_file(path)
        if text is not None:
            findings.extend(text_findings(root, path, text))
    return sorted(findings, key=lambda item: (item.severity, item.path, item.line, item.rule))
