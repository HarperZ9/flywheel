"""test_packaging.py -- what PyPI and the sdist hand a user, read as they get it.

PyPI renders the README with no repository around it, so a relative image or
link resolves against pypi.org and breaks. The sdist is the whole source a
packager or an auditor gets, so it has to carry the docs the README and the
CHANGELOG send a reader to, and every helper the test suite imports. 0.3.0
missed all of these. The sdist here is built the way release.yml builds it,
from a clean copy of the tree through the setuptools build hook, and then read
file by file.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tarfile
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REPO = "HarperZ9/canon"
RAW = f"https://raw.githubusercontent.com/{REPO}/main/"
BLOB = f"https://github.com/{REPO}/blob/main/"
TREE = f"https://github.com/{REPO}/tree/main/"
IMAGE = re.compile(r'!\[[^\]]*\]\(([^)\s]+)\)|<img[^>]*\ssrc="([^"]+)"')
LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)\)|<a[^>]*\shref=\"([^\"]+)\"")
DOC_PATH = re.compile(r"(?<![\w/-])(?:project-docs|docs)/[\w./-]+\.md")
# The README, the CHANGELOG and every user doc the sdist ships name further docs.
NAMED_IN = ("README.md", "CHANGELOG.md", *sorted(p.relative_to(ROOT).as_posix()
                                              for p in (ROOT / "docs").glob("*.md")))
URL_KEYS = ("Homepage", "Source", "Changelog", "Issues")
BUILD = "import sys; from setuptools import build_meta; build_meta.build_sdist(sys.argv[1])"
# Build from what a fresh checkout holds. A leftover egg-info carries an old
# SOURCES.txt that setuptools merges in, which could hide a missing rule.
CLEAN = shutil.ignore_patterns(".git", "__pycache__", "*.egg-info", "build", "dist",
                               ".pytest_cache", ".venv", "venv")


def _targets(pattern: re.Pattern, text: str) -> list[str]:
    return [a or b for a, b in pattern.findall(text)]


def _readme() -> str:
    return (ROOT / "README.md").read_text(encoding="utf-8")


def _named_docs() -> set[str]:
    named = set()
    for source in NAMED_IN:
        text = (ROOT / source).read_text(encoding="utf-8")
        for prefix in (RAW, BLOB, TREE):
            text = text.replace(prefix, "")
        named.update(DOC_PATH.findall(text))
    return named


def test_readme_images_load_from_an_absolute_url_on_main():
    images = _targets(IMAGE, _readme())
    assert images, "the README shows no image, so this check would pass on nothing"
    for target in images:
        assert target.startswith(RAW), f"{target!r} is relative and breaks on PyPI"
        assert (ROOT / target.removeprefix(RAW)).is_file(), f"{target!r} names no file here"


def test_readme_links_resolve_off_github():
    links = _targets(LINK, _readme())
    assert links, "the README links nothing, so this check would pass on nothing"
    for target in links:
        if target.startswith("#"):
            continue
        assert target.startswith("https://"), f"{target!r} is relative and breaks on PyPI"
        for prefix in (BLOB, TREE):
            if target.startswith(prefix):
                path = target.removeprefix(prefix).split("#", 1)[0]
                assert (ROOT / path).exists(), f"{target!r} names no file here"


def test_user_docs_and_examples_name_no_local_path():
    """A drive letter or a home directory in a doc is true on one machine only."""
    shown = [ROOT / "README.md", ROOT / "CHANGELOG.md", *sorted((ROOT / "docs").glob("*.md")),
             *sorted((ROOT / "examples").rglob("*.json"))]
    local = re.compile(r"(?<![\w])[A-Za-z]:[\\/]|/Users/\w|/home/\w")
    found = [f"{path.relative_to(ROOT).as_posix()}: {match.group(0)!r}"
             for path in shown if path.is_file()
             for match in local.finditer(path.read_text(encoding="utf-8"))]
    assert found == []


def test_project_urls_lead_back_to_the_repository():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    urls = project.get("urls", {})
    assert set(URL_KEYS) <= set(urls)
    for name, url in urls.items():
        assert url.startswith(f"https://github.com/{REPO}"), (name, url)


@pytest.fixture(scope="module")
def sdist(tmp_path_factory) -> tuple[Path, set[str]]:
    work = tmp_path_factory.mktemp("sdist")
    tree, out = work / "tree", work / "dist"
    shutil.copytree(ROOT, tree, ignore=CLEAN)
    proc = subprocess.run([sys.executable, "-c", BUILD, str(out)], cwd=tree,
                          capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stderr[-2000:]
    archive = next(out.glob("*.tar.gz"))
    with tarfile.open(archive) as tar:
        names = tar.getnames()
        if hasattr(tarfile, "data_filter"):
            tar.extractall(work / "x", filter="data")
        else:  # pragma: no cover - Python 3.11 before 3.11.4
            tar.extractall(work / "x")
    top = names[0].split("/", 1)[0]
    return work / "x" / top, {name.split("/", 1)[1] for name in names if "/" in name}


def test_sdist_carries_every_doc_the_readme_and_changelog_name(sdist):
    _, shipped = sdist
    named = _named_docs()
    # The docs the 0.3.0 and 0.4.0 releases named, so the check cannot pass on
    # an empty set.
    assert {"docs/switching-models.md", "project-docs/W1-WORKSPACE.md",
            "project-docs/W1-DECISIONS.md", "docs/shared-context.md",
            "project-docs/C1-DECISIONS.md", "project-docs/CONTEXT-STORE-IDENTITY.md"} <= named
    assert sorted(named - shipped) == []


def test_sdist_carries_the_images_the_readme_shows(sdist):
    _, shipped = sdist
    images = {target.removeprefix(RAW) for target in _targets(IMAGE, _readme())}
    assert images and sorted(images - shipped) == []


def test_sdist_carries_what_the_suite_imports_and_reads(sdist):
    _, shipped = sdist
    needed = {p.relative_to(ROOT).as_posix()
              for folder in ("tests", "tools") for p in (ROOT / folder).glob("*.py")}
    needed |= {p.relative_to(ROOT).as_posix() for p in (ROOT / "blocks").glob("*.json")}
    needed |= {"tests/__init__.py", "tests/_helpers.py", "tools/face-metrics.json"}
    assert sorted(needed - shipped) == []


def test_sdist_metadata_carries_the_project_urls(sdist):
    root, _ = sdist
    pkg_info = (root / "PKG-INFO").read_text(encoding="utf-8")
    for name in URL_KEYS:
        assert re.search(rf"^Project-URL: {name}, https://github\.com/{REPO}", pkg_info, re.M), name


def test_the_suite_collects_from_the_extracted_sdist(sdist):
    root, _ = sdist
    proc = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q",
                           "-p", "no:cacheprovider"], cwd=root,
                          capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stdout[-3000:]
    per_file = re.findall(r"^tests/\S+\.py: \d+$", proc.stdout, re.MULTILINE)
    assert len(per_file) == len(list((root / "tests").glob("test_*.py")))
