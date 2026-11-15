"""test_release_workflow.py -- a second run per tag is a no-op, and --version is checked.

release.yml runs on the tag push and again when a GitHub release is published
for that tag. The 0.3.0 release had no skip-existing, so the second run tried
to upload filenames PyPI already had and was cancelled by hand. 0.4.0 added
skip-existing; these checks hold it in place for as long as two events can
start a run for one version. 0.4.0 also resolved its console script in the
smoke step and still answered `canon --version` with a usage error, so the
smoke step now runs `canon --version` from the built wheel and compares it
with the distribution version.

The sdist does not carry .github, so these checks run in a checkout only.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"

pytestmark = pytest.mark.skipif(
    (ROOT / "PKG-INFO").is_file() and not WORKFLOW.exists(),
    reason="an extracted sdist carries no .github directory",
)


def _text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _triggers() -> list[str]:
    block = _text().split("\non:\n", 1)[1].split("\njobs:\n", 1)[0]
    return re.findall(r"^  ([\w-]+):", block, re.MULTILINE)


def _publish_step() -> str:
    return _text().split("pypa/gh-action-pypi-publish@", 1)[1]


def test_a_tag_push_starts_a_release():
    block = _text().split("\non:\n", 1)[1].split("\njobs:\n", 1)[0]
    assert "push" in _triggers()
    assert re.search(r'^    tags: \["v\*"\]$', block, re.MULTILINE)


def test_a_second_run_for_the_same_version_skips_what_pypi_has():
    automatic = [event for event in _triggers() if event != "workflow_dispatch"]
    assert automatic, "no automatic trigger, so this check would pass on nothing"
    # Two automatic events (tag push, then release published) or a manual
    # re-run can each reach the publish step for a version already uploaded.
    assert re.search(r"^\s+skip-existing: true$", _publish_step(), re.MULTILINE)
    assert re.search(r"^\s+attestations: true$", _publish_step(), re.MULTILINE)


def test_the_smoke_step_checks_the_printed_version_against_the_metadata():
    smoke = _text().split("name: no broken release", 1)[1].split("\n      - name:", 1)[0]
    assert '"--version"' in smoke
    assert re.search(r'said == f"canon \{d\.version\}"', smoke)
