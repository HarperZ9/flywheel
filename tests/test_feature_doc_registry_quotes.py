"""The feature pages quote the lane registry as it is.

Several pages in docs/features copy a lane's ``Lane(...)`` entry from
``harness/lanes_registry.py`` or state the version the registry pins. Those
quotes read as observed facts, but nothing checked them, and they lagged each
pin: gather's page showed 1.6.1 while the registry pinned 1.9.1, index's 2.10.0
against 2.13.0, bulletin's 0.2.0 against 0.5.0, calibrate-pro's 1.1.0 against
2.0.0 and telos's 0.2.0 against 0.4.1.

- Every quoted ``"<lane>": Lane(...)`` block is parsed, and each positional
  field and keyword it shows must equal the registry entry. A block may leave
  keywords out; it may not show a different value.
- Every sentence in a lane's page that speaks of the registry (or of a pin) and
  names a version must name the registry's version for that lane.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from harness.lanes_registry import LANES, Lane

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs" / "features"
POSITIONAL = ("name", "install_name", "command", "mcp_args", "kind", "version", "role", "organ")
PAGES = {"accountable-surface.md": "accountable-surface", "articulate.md": "articulate",
         "bulletin.md": "bulletin", "calibrate-pro.md": "calibrate-pro", "canon.md": "canon",
         "chorus-lane.md": "chorus", "crucible.md": "crucible",
         "flywheel-lane-mneme.md": "mneme", "flywheel-lane-plexus.md": "plexus",
         "flywheel-writing-lane.md": "writing", "forum.md": "forum", "gather.md": "gather",
         "index.md": "index", "learn.md": "learn", "local-model.md": "local-model",
         "relay-execution-lane.md": "relay", "telos.md": "telos"}
BLOCK = re.compile(r'^"([a-z-]+)": Lane\((?:.|\n)*?^\s*\S.*\),\s*$', re.M)
VERSION = re.compile(r"version `?(\d+\.\d+\.\d+)`?")


def _blocks() -> list[tuple[str, str, str]]:
    found = []
    for page in sorted(DOCS.glob("*.md")):
        for fence in re.findall(r"```python\n(.*?)```", page.read_text(encoding="utf-8"), re.S):
            if re.search(r'^"[a-z-]+": Lane\(', fence, re.M):
                found.append((page.name, fence))
    return found


def test_the_pages_quote_registry_blocks():
    assert len(_blocks()) >= 8


@pytest.mark.parametrize("page,fence", _blocks(), ids=lambda v: v if v.endswith(".md") else "")
def test_each_quoted_lane_block_matches_the_registry(page, fence):
    tree = ast.parse("{" + fence.strip().rstrip(",") + "}", mode="eval")
    assert isinstance(tree.body, ast.Dict)
    for key, call in zip(tree.body.keys, tree.body.values):
        lane = ast.literal_eval(key)
        assert isinstance(call, ast.Call) and getattr(call.func, "id", "") == Lane.__name__
        entry = LANES[lane]
        for field, node in zip(POSITIONAL, call.args):
            assert ast.literal_eval(node) == getattr(entry, field), (page, lane, field)
        for keyword in call.keywords:
            assert ast.literal_eval(keyword.value) == getattr(entry, keyword.arg), (
                page, lane, keyword.arg)


def _sentences(text: str) -> list[str]:
    flat = " ".join(text.split())
    return [s for s in re.split(r"(?<=[.;])\s+", flat) if s]


@pytest.mark.parametrize("page,lane", sorted(PAGES.items()))
def test_a_registry_sentence_names_the_pinned_version(page, lane):
    text = (DOCS / page).read_text(encoding="utf-8")
    for sentence in _sentences(text):
        if not re.search(r"registry|LANES\[|\bpins\b", sentence):
            continue
        for version in VERSION.findall(sentence):
            assert version == LANES[lane].version, (page, sentence[:160])
