from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SECRET_ASSIGNMENT = re.compile(
    r"""
    (?<![A-Za-z0-9_])
    ["']?
    (?P<name>
        api[_-]?key|
        api[_-]?token|
        access[_-]?token|
        auth[_-]?token|
        client[_-]?secret|
        password|
        passwd|
        secret|
        token
    )
    ["']?
    \s*(?:=|:)\s*
    ["']?
    (?P<value>[A-Za-z0-9][A-Za-z0-9._~+/=-]{15,})
    ["']?
    """,
    re.IGNORECASE | re.VERBOSE,
)
PLACEHOLDER_TERMS = ("placeholder", "example", "sample", "dummy", "redacted", "<")


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_public_and_developer_delivery_files_exist() -> None:
    required = [
        "README.md",
        "USAGE.md",
        "CHANGELOG.md",
        "AUTHORS.md",
        "CONTRIBUTING.md",
        "LICENSE",
        "AGENTS.md",
        ".github/FUNDING.yml",
        ".github/workflows/ci.yml",
        "docs/art/social.png",
        "project-docs/specs/SPEC-repo-proof-index-forward-delivery.md",
    ]

    assert [path for path in required if not (ROOT / path).is_file()] == []


def test_readme_and_usage_describe_public_and_developer_paths() -> None:
    readme = read("README.md")
    usage = read("USAGE.md")

    for heading in ["## Why it matters", "## Try it", "## For developers"]:
        assert heading in readme
    assert "docs/art/hero-light.svg" in readme
    assert "reviewer-ready index" in readme.lower()
    assert "python -m pytest" in readme
    assert "Usage" in usage
    assert "repo-proof-index" in usage


def test_changelog_records_delivery_contract() -> None:
    text = read("CHANGELOG.md")

    assert "Forward Delivery Contract" in text
    assert "SPEC-repo-proof-index-forward-delivery.md" in text


def test_docs_do_not_use_credential_shaped_assignments() -> None:
    docs = ["README.md", "USAGE.md", "CHANGELOG.md", "AGENTS.md"]
    findings: list[str] = []

    for path in docs:
        text = read(path)
        for match in SECRET_ASSIGNMENT.finditer(text):
            value = match.group("value").lower()
            if not any(term in value for term in PLACEHOLDER_TERMS):
                line = text[: match.start()].count("\n") + 1
                findings.append(f"{path}:{line}")

    assert findings == []
