"""The Homebrew formula and the Scoop manifest install the declared release.

Formula/flywheel.rb and bucket/flywheel.json each pin one PyPI file by URL and
SHA-256. A release that bumps pyproject.toml and never updates them would keep
`brew install flywheel` and `scoop install flywheel` on the old version with
nothing failing. These tests fail on that drift.

The digests exist only after PyPI has the release, so the release PR cannot
carry them. The files may trail pyproject.toml by exactly one release (the
newest root RELEASE-NOTES below the declared version) until the follow-up PR
from scripts/package_manager_bump.py lands. With FLYWHEEL_CHECK_PYPI=1 the last
test also asks PyPI: the pinned digests must match it byte for byte, and once
PyPI has the declared version the files must pin it, which closes that window.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FORMULA = ROOT / "Formula" / "flywheel.rb"
MANIFEST = ROOT / "bucket" / "flywheel.json"
SHA256 = re.compile(r"[0-9a-f]{64}")


def _bump():
    spec = importlib.util.spec_from_file_location(
        "package_manager_bump", ROOT / "scripts" / "package_manager_bump.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _formula() -> dict[str, str]:
    text = FORMULA.read_text(encoding="utf-8")
    url = re.findall(r'^  url "([^"]+)"$', text, re.M)
    sha = re.findall(r'^  sha256 "([^"]+)"$', text, re.M)
    assert len(url) == 1 and len(sha) == 1, "the formula pins exactly one url and one sha256"
    m = re.fullmatch(r"https://files\.pythonhosted\.org/packages/[0-9a-f]{2}/[0-9a-f]{2}/"
                     r"[0-9a-f]{60}/flywheel_verify-(\d+\.\d+\.\d+)\.tar\.gz", url[0])
    assert m, f"the formula url is not a PyPI flywheel-verify sdist: {url[0]}"
    return {"text": text, "url": url[0], "sha256": sha[0], "version": m.group(1)}


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _versions_allowed() -> set[str]:
    declared = _bump().pyproject_version()
    key = tuple(int(p) for p in declared.split("."))
    released = [tuple(int(p) for p in m.groups()) for path in ROOT.glob("RELEASE-NOTES-*.md")
                if (m := re.fullmatch(r"RELEASE-NOTES-(\d+)\.(\d+)\.(\d+)\.md", path.name))]
    below = [v for v in released if v < key]
    return {declared} | ({".".join(map(str, max(below)))} if below else set())


def test_the_formula_is_a_virtualenv_install_of_the_sdist():
    formula = _formula()
    text = formula["text"]
    assert "class Flywheel < Formula" in text
    assert "include Language::Python::Virtualenv" in text
    assert "virtualenv_install_with_resources" in text
    assert re.search(r'^  depends_on "python@3\.1[1-9]"$', text, re.M)
    assert not re.search(r'^\s*resource "', text, re.M), "zero runtime dependencies: a resource block is a mistake"
    assert SHA256.fullmatch(formula["sha256"])
    assert '#{bin}/flywheel --version' in text, "the formula test runs the installed command"


def test_the_scoop_manifest_installs_the_wheel_into_a_venv():
    manifest = _manifest()
    version = manifest["version"]
    assert manifest["url"] == _bump().WHEEL_URL.format(version=version)
    assert SHA256.fullmatch(manifest["hash"])
    assert manifest["depends"] == "python"
    assert manifest["bin"] == [["venv\\Scripts\\flywheel.exe", "flywheel"]]
    script = "\n".join(manifest["installer"]["script"])
    assert "-m venv" in script and "--no-index --no-deps" in script and "$fname" in script
    assert script.count("$LASTEXITCODE -ne 0") == 2, "a failed venv or pip step must fail the install"
    assert manifest["checkver"]["url"] == "https://pypi.org/pypi/flywheel-verify/json"
    auto = manifest["autoupdate"]
    assert auto["url"] == _bump().WHEEL_URL.format(version="$version")
    assert "$version" in auto["hash"]["url"] and "bdist_wheel" in auto["hash"]["jsonpath"]


def test_both_package_managers_name_the_same_release():
    assert _formula()["version"] == _manifest()["version"]


def test_the_package_managers_install_the_declared_or_the_just_released_version():
    pinned = _manifest()["version"]
    allowed = _versions_allowed()
    assert pinned in allowed, (
        f"Formula and Scoop manifest pin {pinned}, expected one of {sorted(allowed)}: "
        "after the release is on PyPI, run python scripts/package_manager_bump.py")


def test_the_bump_rewrites_only_the_pinned_lines():
    bump = _bump()
    release = {"sdist_url": "https://files.pythonhosted.org/packages/ab/cd/" + "e" * 60
                            + "/flywheel_verify-9.9.9.tar.gz",
               "sdist_sha256": "1" * 64, "wheel_sha256": "2" * 64}
    text = FORMULA.read_text(encoding="utf-8")
    new = bump.render_formula(text, release)
    assert release["sdist_url"] in new and release["sdist_sha256"] in new
    assert len(new.splitlines()) == len(text.splitlines())
    manifest = json.loads(bump.render_manifest(MANIFEST.read_text(encoding="utf-8"), "9.9.9", release))
    assert manifest["version"] == "9.9.9" and manifest["hash"] == "2" * 64
    assert manifest["url"].endswith("/flywheel_verify-9.9.9-py3-none-any.whl")
    assert manifest["autoupdate"] == _manifest()["autoupdate"]


@pytest.mark.skipif(os.environ.get("FLYWHEEL_CHECK_PYPI") != "1",
                    reason="asks PyPI over the network; set FLYWHEEL_CHECK_PYPI=1")
def test_the_pinned_digests_match_pypi():
    bump = _bump()
    pinned, declared = _manifest()["version"], bump.pyproject_version()
    assert bump.main(["--check", pinned]) == 0
    if pinned != declared:
        assert not bump.pypi_has(declared), (
            f"PyPI has {declared} but the formula and manifest still pin {pinned}: "
            "run python scripts/package_manager_bump.py and commit the two files")
