from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
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
PLACEHOLDER_TERMS = ("placeholder", "redacted", "example", "dummy", "sample", "<")


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


class ForwardDeliveryContractTests(unittest.TestCase):
    def test_root_delivery_files_are_present(self) -> None:
        required = [
            "README.md",
            "USAGE.md",
            "CHANGELOG.md",
            "AUTHORS.md",
            "CONTRIBUTING.md",
            "LICENSE",
            ".github/FUNDING.yml",
            ".github/workflows/conformance.yml",
            "assets/emet-hero.png",
            ".github/assets/banner.png",
        ]

        missing = [path for path in required if not (ROOT / path).is_file()]

        self.assertEqual(missing, [])

    def test_readme_has_public_and_developer_delivery_sections(self) -> None:
        text = read("README.md")

        for heading in ["## Why it matters", "## Usage", "## For developers"]:
            self.assertIn(heading, text)
        # The front page leads with the hero in both themes (4 October 2026); each PNG
        # rendered with it carries a receipt in docs/art/receipts.json.
        self.assertIn("docs/art/hero-light.svg", text)
        self.assertIn("docs/art/hero-dark.svg", text)
        self.assertIn("public value", text.lower())
        self.assertIn("advisory integrity witness", text.lower())
        self.assertIn("python test_forward_delivery_contract.py", text)

    def test_changelog_records_current_delivery_status(self) -> None:
        text = read("CHANGELOG.md")

        self.assertIn("EMET Forward Delivery Contract", text)
        self.assertIn("public-surface-sweeper", text)
        self.assertIn("advisory-only", text)

    def test_documentation_uses_placeholders_for_secret_assignments(self) -> None:
        docs = [
            "docs/scope-discipline/G2-closed-lattice.md",
            "docs/scope-discipline/G4-advisory.md",
            "docs/scope-discipline/G6-no-adjudication.md",
        ]

        findings: list[str] = []
        for path in docs:
            text = read(path)
            for match in SECRET_ASSIGNMENT.finditer(text):
                value = match.group("value").lower()
                if not any(term in value for term in PLACEHOLDER_TERMS):
                    findings.append(f"{path}:{text[:match.start()].count(chr(10)) + 1}")

        self.assertEqual(findings, [])


if __name__ == "__main__":
    unittest.main()
