"""Each lane doc states one install path, and it agrees with the registry
(design 7.13, FW-14, F-12).

The registry's `package_disabled_reason` says whether a lane's package is an
admitted distribution. A doc may not say the package is published and also
that it is not, and may not contradict the registry. The registry is read and
never edited here.
"""
from pathlib import Path
import re

import pytest

from harness.lanes_registry import LANES

ROOT = Path(__file__).resolve().parents[1]
FEATURES = ROOT / "docs" / "features"
NOT_PUBLISHED = re.compile(
    r"(?i)not distributable|name is disabled|package is disabled|"
    r"not an admitted distribution|no published (?:npm |pypi )?distribution|"
    r"is not published|never published")
PUBLISHED = re.compile(
    r"(?i)distribution is published|publishes as|is published on|"
    r"`(?:pip|npm) install [a-z@]")


def _lane_docs():
    docs = sorted(FEATURES.glob("*.md"))
    for key in sorted(LANES):
        for doc in docs:
            if key in doc.stem:
                yield key, doc


def _normalized(path):
    return " ".join(path.read_text(encoding="utf-8").split())


@pytest.mark.parametrize("key,doc", list(_lane_docs()), ids=lambda v: str(v))
def test_a_lane_doc_agrees_with_the_registry(key, doc):
    text = _normalized(doc)
    disabled = bool(LANES[key].package_disabled_reason)
    says_not = NOT_PUBLISHED.findall(text)
    says_yes = PUBLISHED.findall(text)
    if disabled:
        assert not says_yes, f"{doc.name} claims a published package: {says_yes}"
    else:
        assert not says_not, f"{doc.name} says the package is unavailable: {says_not}"


def test_the_two_docs_the_audit_named_are_covered():
    covered = {(k, d.name) for k, d in _lane_docs()}
    assert ("mneme", "flywheel-lane-mneme.md") in covered
    assert ("canon", "canon.md") in covered


def test_lane_docs_point_at_the_registry_for_the_version():
    for name in ("flywheel-lane-mneme.md", "canon.md"):
        text = _normalized(FEATURES / name)
        assert "harness/lanes_registry.py" in text, name
        assert not re.search(r"(?i)version\s*`?\d+\.\d+\.\d+`?\s*\(read from the registry",
                             text), name


def test_the_checker_catches_a_contradiction():
    """False-success control: the patterns must see the audit's contradiction."""
    shipped = ("`flywheel install --lanes canon --profile source` (source profile, "
               "since the package is not distributable).")
    assert NOT_PUBLISHED.search(shipped)
    assert PUBLISHED.search("Install it with `pip install flywheel-canon`.")
