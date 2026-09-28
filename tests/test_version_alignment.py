"""Falsifiers for the one-version invariant across the shipping surfaces.

One tag ships the platform: publish.yml sends the engine wheel to PyPI and
desktop-release.yml builds the Windows installer, both gated on the same
version. These fail the moment the three declarations drift (pyproject.toml
for the wheel, desktop/pubspec.yaml for the installer, desktop/lib/version.dart
for the About surface), or the release pipeline regresses to freezing the
engine from the archived predecessor repo.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _pyproject_version():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*"(.+?)"', text, re.M)
    assert m, "no version declaration found in pyproject.toml"
    return m.group(1)


def _pubspec_version():
    text = (ROOT / "desktop" / "pubspec.yaml").read_text(encoding="utf-8")
    m = re.search(r"^version:\s*(.+)$", text, re.M)
    assert m, "no version declaration found in desktop/pubspec.yaml"
    return m.group(1).split("+")[0].strip()


def _version_dart():
    text = (ROOT / "desktop" / "lib" / "version.dart").read_text(encoding="utf-8")
    m = re.search(r"appVersion\s*=\s*['\"](.+?)['\"]", text)
    assert m, "no appVersion declaration found in desktop/lib/version.dart"
    return m.group(1)


def test_engine_and_desktop_declare_one_version():
    py, pub, dart = _pyproject_version(), _pubspec_version(), _version_dart()
    assert py == pub == dart, (
        f"version drift: pyproject={py} pubspec={pub} version.dart={dart} "
        "-- one platform, one version; bump all three together"
    )


def test_desktop_release_builds_from_this_repo():
    wf = ROOT / ".github" / "workflows" / "desktop-release.yml"
    assert wf.exists(), (
        "desktop-release.yml must live in the ROOT workflows dir; "
        "GitHub Actions never runs a nested .github/"
    )
    text = wf.read_text(encoding="utf-8")
    assert "local-model" not in text, (
        "the installer engine must freeze from this monorepo, "
        "not the archived predecessor repo"
    )
    assert "repository:" not in text, (
        "no external checkout: both halves live in this repo"
    )


def test_stale_nested_desktop_workflows_are_gone():
    assert not (ROOT / "desktop" / ".github").exists(), (
        "desktop/.github/ is dead weight: GitHub Actions only runs root "
        "workflows, so anything here silently never executes"
    )


def test_one_tag_triggers_both_shipping_workflows():
    # The invariant is two-sided: the wheel (publish.yml) and the installer
    # (desktop-release.yml) must both fire on the same v* tag push.
    tag_pattern = re.compile(r'tags:\s*(\[\s*"v\*"\s*\]|(\r?\n\s*-\s*"v\*"))')
    for name in ("publish.yml", "desktop-release.yml"):
        wf = ROOT / ".github" / "workflows" / name
        assert wf.exists(), f"{name} is a shipping half and must exist"
        text = wf.read_text(encoding="utf-8")
        assert tag_pattern.search(text), (
            f"{name} must trigger on v* tag pushes; one tag ships the platform"
        )


def test_the_next_release_notes_name_the_declared_version():
    # The release notes and the three declarations move together: a bump that
    # leaves the notes on another number (or the notes ahead of the sites)
    # fails here before a tag is cut from either.
    draft = ROOT / f"RELEASE-NOTES-{_pyproject_version()}.md"
    heading = next(line for line in draft.read_text(encoding="utf-8").splitlines()
                   if line.startswith("# "))
    assert heading == f"# Flywheel {_pyproject_version()}", heading


def test_the_minor_number_moved_for_the_unlisted_tool_change():
    # O-12 changes what pip and source installs do with an unlisted lane tool,
    # so the release carrying it is 1.1.0, not a 1.0.x patch.
    from harness.lane_caller import UNLISTED_TOOL_TIER
    major, minor, _patch = (int(part) for part in _pyproject_version().split("."))
    assert UNLISTED_TOOL_TIER == "T2" and (major, minor) >= (1, 1)
