"""Repository checks against small fixture repositories built in a temp dir."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from discover import cff, text
from discover.repo import check_repo

README_GOOD = """<picture><img src="x.svg"></picture>

# tool

Tool checks your files for drift and tells you which ones changed.

```bash
pip install tool
tool check .
```
"""

CFF_GOOD = """cff-version: 1.2.0
message: "If you use this software, please cite it as below."
title: "tool"
version: "1.2.0"
date-released: 2026-10-23
authors:
  - family-names: "Harper"
    given-names: "Zain Dana"
repository-code: "https://github.com/o/tool"
keywords:
  - drift
"""

PYPROJECT_GOOD = """[project]
name = "tool"
version = "1.2.0"
description = "Checks files for drift."
keywords = ["drift", "hash", "integrity"]
classifiers = ["Development Status :: 4 - Beta", "Topic :: Utilities",
               "Programming Language :: Python :: 3"]
[project.urls]
Homepage = "https://example.org"
Repository = "https://github.com/o/tool"
"""

CHANGELOG_GOOD = """# Changelog

## 1.2.0 (2026-10-23)

Tool now tells you which files drifted since the last check, in one line each.

- Added `tool check`.
"""


def build(files: dict[str, str]) -> Path:
    root = Path(tempfile.mkdtemp())
    for name, body in files.items():
        (root / name).write_text(body, encoding="utf-8")
    return root


def failed(report) -> set[str]:
    return {f.check for f in report.failures}


class RepoChecks(unittest.TestCase):
    def test_complete_repo_has_no_blocking_failure(self) -> None:
        root = build({"README.md": README_GOOD, "CITATION.cff": CFF_GOOD,
                      "pyproject.toml": PYPROJECT_GOOD, "CHANGELOG.md": CHANGELOG_GOOD})
        report = check_repo(root, offline=True, version="v1.2.0")
        self.assertEqual([f.check for f in report.blocking], [])
        self.assertIn("github.metadata", failed(report))  # offline is a warning, never a pass

    def test_missing_pieces_block(self) -> None:
        root = build({"README.md": "# tool\n\n- a list first\n", "pyproject.toml": "[project]\nname='t'\n"})
        report = check_repo(root, offline=True)
        for check in ("readme.benefit_first", "readme.run_command", "citation.valid",
                      "package.keywords", "package.classifiers", "release.summary"):
            self.assertIn(check, failed(report), check)
        self.assertFalse(report.passes())

    def test_release_notes_must_lead_with_a_sentence(self) -> None:
        log = "## 2.0.0\n\n### Added\n- thing\n- other\n"
        root = build({"CHANGELOG.md": log})
        report = check_repo(root, offline=True, version="2.0.0")
        self.assertIn("release.summary", failed(report))

    def test_citation_version_must_match_the_release(self) -> None:
        root = build({"CITATION.cff": CFF_GOOD, "pyproject.toml": PYPROJECT_GOOD})
        report = check_repo(root, offline=True, version="1.3.0")
        self.assertIn("citation.valid", failed(report))

    def test_package_json_keywords(self) -> None:
        pkg = {"name": "t", "version": "1.0.0", "description": "d", "keywords": ["a"],
               "repository": {"type": "git", "url": "x"}}
        root = build({"package.json": json.dumps(pkg)})
        self.assertIn("package.keywords", failed(check_repo(root, offline=True)))


class TextHelpers(unittest.TestCase):
    def test_first_paragraph_skips_badges_and_html(self) -> None:
        lines = README_GOOD.splitlines()
        line, para = text.first_paragraph(lines)
        self.assertTrue(para.startswith("Tool checks your files"))

    def test_first_command_ignores_python_blocks(self) -> None:
        lines = ["# t", "```python", "import t", "```", "```", "$ t run", "```"]
        self.assertEqual(text.first_command(lines, 60)[1], "$ t run")

    def test_section_by_version(self) -> None:
        found = text.changelog_section(CHANGELOG_GOOD, "1.2.0")
        self.assertTrue(found and found[0].startswith("## 1.2.0"))
        self.assertIsNone(text.changelog_section(CHANGELOG_GOOD, "1.2"))

    def test_cff_parse_and_problems(self) -> None:
        data = cff.parse(CFF_GOOD)
        self.assertEqual(data["authors"][0]["family-names"], "Harper")
        self.assertEqual(cff.problems(data, "1.2.0"), [])
        self.assertTrue(cff.problems({"title": "x"}))


if __name__ == "__main__":
    unittest.main()
