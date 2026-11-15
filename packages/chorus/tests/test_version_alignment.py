"""The declared version must agree everywhere it is written down.

chorus declares its version twice: once in ``pyproject.toml`` for the built
distribution and once as ``chorus.__version__`` for anything that asks the
running package what it is. Nothing previously tied the two together, so a
release could ship 0.3.1 while the module reported 0.3.0 and every test still
passed. The release workflow checks the git tag against ``pyproject.toml`` and
would not have caught it either, because it never reads the module.

The version is read with a regex rather than ``tomllib``. ``requires-python`` is
``>=3.10`` and ``tomllib`` arrived in 3.11, so importing it here would make the
guard itself the reason the 3.10 job fails.
"""
from __future__ import annotations

import pathlib
import re

import chorus

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_PROJECT_VERSION = re.compile(
    r"^\[project\]$.*?^version\s*=\s*[\"']([^\"']+)[\"']",
    re.MULTILINE | re.DOTALL,
)


def _declared_version() -> str:
    text = (_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = _PROJECT_VERSION.search(text)
    assert match is not None, "pyproject.toml has no [project] version"
    return match.group(1)


def test_the_declared_version_is_readable():
    # Guards the guard: a regex that silently stops matching would make both
    # assertions below vacuous rather than failing.
    assert re.fullmatch(r"\d+\.\d+\.\d+", _declared_version())


def test_module_version_matches_the_declared_distribution_version():
    assert chorus.__version__ == _declared_version()


def test_the_changelog_has_an_entry_for_the_declared_version():
    changelog = (_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    version = _declared_version()
    assert f"## {version}" in changelog, (
        f"CHANGELOG.md has no '## {version}' heading, so the release would ship "
        "without saying what changed")
