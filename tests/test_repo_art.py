"""The front-page artwork stays true to the words it illustrates.

A picture in a README is never diffed, so it drifts from the text silently:
somebody edits a stage name, nobody re-renders, and the diagram now describes
a version of the tool that no longer exists. Here the picture is a pure
function of a spec that IS diffable, and this re-renders it and compares
bytes.

The last test is the one that found real work. This repository already
carried two canon-correct schematics that NOTHING linked to, so a reader
never saw them. Unreferenced artwork is the same defect as stale artwork:
the reader gets nothing either way.
"""
import importlib.util
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ART = ROOT / "docs" / "art"


def _load(name):
    spec = importlib.util.spec_from_file_location(
        name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


R = _load("repo_art")
RENDER = _load("render_repo_art")

SPECS = sorted(ART.glob("*.art.json"))


def test_there_is_at_least_one_spec():
    assert SPECS, "docs/art holds no *.art.json spec"


@pytest.mark.parametrize("spec_path", SPECS, ids=lambda p: p.name)
def test_committed_artwork_matches_its_spec(spec_path):
    for path, text in RENDER.rendered(spec_path).items():
        assert path.exists(), f"{path.name} was never rendered"
        assert path.read_text(encoding="utf-8") == text + "\n", (
            f"{path.name} is stale; run python scripts/render_repo_art.py")


@pytest.mark.parametrize("spec_path", SPECS, ids=lambda p: p.name)
def test_rendering_twice_gives_the_same_bytes(spec_path):
    """The corona is random draws. Seeded ones, or this fails."""
    first = RENDER.rendered(spec_path)
    second = RENDER.rendered(spec_path)
    assert first == second


def test_each_repository_gets_its_own_drawing():
    """The identity claim, checked rather than asserted in a doc."""
    names = ["flywheel", "gather", "crucible", "index", "forum", "telos"]
    marks = {n: R.header_svg(
        {"name": n, "role": "x", "tagline": "y", "words": ["z"]}) for n in names}
    assert len({R.seed_for(n) for n in names}) == len(names)
    bodies = {n: re.sub(r"[A-Z]{3,}", "", svg) for n, svg in marks.items()}
    assert len(set(bodies.values())) == len(names), "two repositories drew alike"


def test_the_seed_is_recorded_on_the_mark():
    """Canon: a generated mark carries the seed that made it."""
    svg = R.header_svg({"name": "flywheel", "role": "x", "tagline": "y",
                        "words": []})
    assert f"SEED {R.seed_for('flywheel') % 100000:05d}" in svg


def test_no_local_paths_or_em_dashes_in_the_art():
    for path in sorted(ART.glob("*.svg")):
        text = path.read_text(encoding="utf-8")
        assert "\u2014" not in text, f"{path.name} carries an em-dash"
        assert not re.search(r"[A-Z]:[\/]", text), f"{path.name} names a path"


def test_the_spec_words_reach_the_drawing():
    """Guards against a diagram that renders but silently drops content."""
    for spec_path in SPECS:
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        rendered = "".join(RENDER.rendered(spec_path).values())
        assert spec["header"]["tagline"] in rendered
        for flow in spec.get("flows", []):
            for stage in flow["stages"]:
                assert stage["title"] in rendered, stage["title"]


# Where an illustration lives. `docs/assets/` is deliberately outside this
# set: it holds source material rather than illustration. The banner card
# there is 1280x640, the ratio GitHub wants for a repository's social preview,
# and that image is uploaded through the repository settings instead of being
# linked from prose. Requiring prose to carry it would put a link-preview image
# in the middle of a paragraph that has no use for one.
SHOWN_DIRS = ("docs/art", "docs/schematics")


def test_every_illustration_is_actually_shown_to_a_reader():
    """No orphans. An image nobody links to is an image nobody sees."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    docs = "".join(p.read_text(encoding="utf-8", errors="ignore")
                   for p in ROOT.glob("docs/**/*.md"))
    haystack = readme + docs
    images = sorted(p for d in SHOWN_DIRS for p in (ROOT / d).glob("*")
                    if p.suffix.lower() in {".svg", ".png"})
    orphans = [str(p.relative_to(ROOT)).replace("\\", "/")
               for p in images
               if str(p.relative_to(ROOT)).replace("\\", "/") not in haystack]
    assert not orphans, f"committed but never shown: {orphans}"
