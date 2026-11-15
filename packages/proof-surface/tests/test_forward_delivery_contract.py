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
LOCAL_MACHINE_PATH = re.compile(
    r"(?:[A-Za-z]:[\\/](?:dev|Users)\b|/(?:c|e)/(?:dev|Users)\b)",
    re.IGNORECASE,
)
PUBLIC_DOCS = ["README.md", "USAGE.md", "CHANGELOG.md", "AGENTS.md"]
NEW_CONTRACT_ARTIFACTS = [
    "schemas/authorization-receipt-v0.2.schema.json",
    "schemas/organ-receipt-bundle.schema.json",
    "conformance/authorization-receipt/v0.2/manifest.json",
    "conformance/authorization-receipt/v0.2/valid/minimal.receipt.json",
    "conformance/authorization-receipt/v0.2/invalid/short-nonce.receipt.json",
    "conformance/authorization-receipt/v0.2/invalid/unknown-root-field.receipt.json",
    "conformance/authorization-receipt/v0.2/migration/migrated-v0.2.receipt.json",
    "conformance/organ-receipt-bundle/v0.1/manifest.json",
    "conformance/organ-receipt-bundle/v0.1/valid/tadr-kinds.bundle.json",
    "conformance/organ-receipt-bundle/v0.1/invalid/tadr-zero-digest.bundle.json",
]


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
        "scripts/check_public_surface.py",
        "docs/art/social.png",
        "project-docs/specs/SPEC-proof-surface-forward-delivery.md",
    ]

    assert [path for path in required if not (ROOT / path).is_file()] == []


def test_readme_serves_public_and_developer_audiences() -> None:
    text = read("README.md")

    for heading in ["## Try it", "## Why it matters", "## For developers"]:
        assert heading in text
    assert "docs/art/hero-light.svg" in text
    assert "validate evidence packets" in text.lower()
    assert "USAGE.md" in text
    assert "CHANGELOG.md" in text
    assert 'python -m pip install -e ".[test]"' in text
    assert "python -m pytest" in text


def test_changelog_records_current_delivery_status() -> None:
    text = read("CHANGELOG.md")

    assert "Forward Delivery Contract" in text
    assert "SPEC-proof-surface-forward-delivery.md" in text
    assert "validators" in text


def test_docs_do_not_use_credential_shaped_assignments() -> None:
    findings: list[str] = []

    for path in PUBLIC_DOCS + NEW_CONTRACT_ARTIFACTS:
        text = read(path)
        for match in SECRET_ASSIGNMENT.finditer(text):
            value = match.group("value").lower()
            if not any(term in value for term in PLACEHOLDER_TERMS):
                line = text[: match.start()].count("\n") + 1
                findings.append(f"{path}:{line}")

    assert findings == []


def test_public_docs_and_new_contract_artifacts_have_no_machine_paths() -> None:
    findings: list[str] = []

    for path in PUBLIC_DOCS + NEW_CONTRACT_ARTIFACTS:
        for line_number, line in enumerate(read(path).splitlines(), 1):
            if LOCAL_MACHINE_PATH.search(line):
                findings.append(f"{path}:{line_number}")

    assert findings == []
