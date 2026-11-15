import re
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "tools" / "check_release_metadata.py"
EXPECTED_VERSION = "0.7.0"


def _run_guard(root: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    return subprocess.run(
        [sys.executable, str(GUARD), "--root", str(root), "--expected-version", EXPECTED_VERSION, *extra],
        text=True,
        capture_output=True,
        cwd=ROOT,
        env=env,
        timeout=12,
    )


def _copy_release_files(tmp_path: Path) -> Path:
    dest = tmp_path / "relay"
    for relative in (
        "pyproject.toml",
        "CHANGELOG.md",
        "README.md",
        "docs/GITHUB-ONLY-INSTALL.md",
        "src/relay/__init__.py",
        "src/relay/local_mcp.py",
    ):
        target = dest / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
    return dest


def test_release_metadata_guard_accepts_0_2_3_tree():
    result = _run_guard(ROOT)

    assert result.returncode == 0, result.stdout + result.stderr


def test_release_metadata_guard_rejects_stale_github_release_example(tmp_path):
    root = _copy_release_files(tmp_path)
    guide = root / "docs" / "GITHUB-ONLY-INSTALL.md"
    guide.write_text(
        guide.read_text(encoding="utf-8").replace("v0.7.0", "v0.2.4"),
        encoding="utf-8",
    )

    result = _run_guard(root)

    assert result.returncode == 1
    assert "docs/GITHUB-ONLY-INSTALL.md" in result.stderr
    assert "0.7.0" in result.stderr


def test_release_metadata_guard_rejects_package_version_mismatch(tmp_path):
    root = _copy_release_files(tmp_path)
    project = root / "pyproject.toml"
    project.write_text(
        project.read_text(encoding="utf-8").replace('version = "0.7.0"', 'version = "0.2.4"'),
        encoding="utf-8",
    )

    result = _run_guard(root)

    assert result.returncode == 1
    assert "pyproject.toml" in result.stderr
    assert "0.7.0" in result.stderr



def test_release_metadata_guard_rejects_temporary_availability_language(tmp_path):
    root = _copy_release_files(tmp_path)
    changelog = root / "CHANGELOG.md"
    # Matched by regex with \s+ between words rather than as a literal block:
    # the CHANGELOG is hard-wrapped, so a literal match silently does nothing the
    # moment a line is reflowed, and the test then passes an unmodified file to
    # the guard and asserts a rejection that cannot happen.
    original = changelog.read_text(encoding="utf-8")
    pattern = re.compile(
        r"Source\s+version\s+metadata\s+is\s+not\s+release\s+availability\s+proof;\s+"
        r"release\s+availability\s+is\s+established\s+only\s+by\s+the\s+accepted\s+Git\s+"
        r"tag,\s+uploaded\s+GitHub\s+Release\s+assets,\s+and\s+matching\s+hash\s+readback\."
    )
    # count=1: every past release section repeats this sentence, and the guard
    # only inspects the top one. Replacing the first occurrence is what makes the
    # top section stale, which is the condition under test.
    replaced, count = pattern.subn(
        "This is prospective 0.7.0 source metadata only. The latest already published "
        "GitHub Release remains 0.2.4 until the release owner publishes 0.7.0 assets.",
        original,
        count=1,
    )
    assert count == 1, "the availability-boundary sentence was not found to replace"
    changelog.write_text(replaced, encoding="utf-8")

    result = _run_guard(root)

    assert result.returncode == 1
    assert "CHANGELOG.md" in result.stderr
    assert "release availability" in result.stderr


def test_release_metadata_guard_rejects_install_guide_without_fail_closed_checksum(tmp_path):
    root = _copy_release_files(tmp_path)
    guide = root / "docs" / "GITHUB-ONLY-INSTALL.md"
    guide.write_text(
        guide.read_text(encoding="utf-8").replace(
            "Do not continue to `pip install` if the wheel has no checksum line or the computed hash differs.",
            "",
        ),
        encoding="utf-8",
    )

    result = _run_guard(root)

    assert result.returncode == 1
    assert "docs/GITHUB-ONLY-INSTALL.md" in result.stderr
    assert "pip install" in result.stderr



def _release_wheel_recipe() -> str:
    import re

    guide = (ROOT / "docs" / "GITHUB-ONLY-INSTALL.md").read_text(encoding="utf-8")
    match = re.search(r"```powershell\n(?P<recipe>.*?)\n```", guide, re.S)
    assert match, "missing powershell release wheel recipe"
    return match.group("recipe")


def _powershell_exe() -> str:
    import shutil

    exe = shutil.which("pwsh") or shutil.which("powershell")
    if not exe:
        import pytest

        pytest.skip("PowerShell is not available for executable install recipe test")
    return exe


def _write_fake_python(bin_dir: Path, log_path: Path) -> None:
    if os.name == "nt":
        fake = bin_dir / "python.cmd"
        fake.write_text('@echo off\necho %*>> "%FAKE_PYTHON_LOG%"\nexit /b 0\n', encoding="utf-8")
    else:
        fake = bin_dir / "python"
        fake.write_text('#!/usr/bin/env sh\nprintf "%s\\n" "$*" >> "$FAKE_PYTHON_LOG"\nexit 0\n', encoding="utf-8")
        fake.chmod(0o755)


def _run_release_wheel_recipe(tmp_path: Path, checksum_lines: list[str]):
    import hashlib

    recipe = _release_wheel_recipe()
    wheel = tmp_path / "flywheel_relay-0.7.0-py3-none-any.whl"
    wheel.write_bytes(b"fake relay wheel bytes\n")
    actual_hash = hashlib.sha256(wheel.read_bytes()).hexdigest()
    rendered = [line.replace("{actual}", actual_hash) for line in checksum_lines]
    (tmp_path / "SHA256SUMS.txt").write_text("\n".join(rendered) + ("\n" if rendered else ""), encoding="utf-8")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log_path = tmp_path / "fake-python.log"
    _write_fake_python(bin_dir, log_path)

    env = {**os.environ, "FAKE_PYTHON_LOG": str(log_path)}
    env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
    result = subprocess.run(
        [_powershell_exe(), "-NoProfile", "-NonInteractive", "-Command", recipe],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        timeout=15,
    )
    return result, log_path.read_text(encoding="utf-8") if log_path.exists() else ""


def test_release_wheel_recipe_is_single_stop_on_error_invocation():
    recipe = _release_wheel_recipe().strip()

    assert recipe.startswith("& {")
    assert "$ErrorActionPreference = \"Stop\"" in recipe or "$ErrorActionPreference = 'Stop'" in recipe


def test_release_wheel_recipe_installs_after_exactly_one_valid_checksum(tmp_path):
    line = "{actual}  flywheel_relay-0.7.0-py3-none-any.whl"

    result, fake_python_log = _run_release_wheel_recipe(tmp_path, [line])

    assert result.returncode == 0, result.stdout + result.stderr
    assert "-m pip install --no-index" in fake_python_log
    assert "flywheel_relay-0.7.0-py3-none-any.whl" in fake_python_log


def test_release_wheel_recipe_stops_before_pip_when_checksum_missing(tmp_path):
    result, fake_python_log = _run_release_wheel_recipe(tmp_path, [])

    assert result.returncode != 0
    assert "missing" in result.stderr.lower() or "exactly one" in result.stderr.lower()
    assert fake_python_log == ""


def test_release_wheel_recipe_stops_before_pip_when_checksum_mismatches(tmp_path):
    bad = "0" * 64 + "  flywheel_relay-0.7.0-py3-none-any.whl"

    result, fake_python_log = _run_release_wheel_recipe(tmp_path, [bad])

    assert result.returncode != 0
    assert "mismatch" in result.stderr.lower()
    assert fake_python_log == ""


def test_release_wheel_recipe_stops_before_pip_when_duplicate_same_checksum(tmp_path):
    line = "{actual}  flywheel_relay-0.7.0-py3-none-any.whl"

    result, fake_python_log = _run_release_wheel_recipe(tmp_path, [line, line])

    assert result.returncode != 0
    assert "exactly one" in result.stderr.lower()
    assert fake_python_log == ""


def test_release_wheel_recipe_stops_before_pip_when_duplicate_conflicting_checksum(tmp_path):
    good = "{actual}  flywheel_relay-0.7.0-py3-none-any.whl"
    bad = "0" * 64 + "  flywheel_relay-0.7.0-py3-none-any.whl"

    result, fake_python_log = _run_release_wheel_recipe(tmp_path, [good, bad])

    assert result.returncode != 0
    assert "exactly one" in result.stderr.lower()
    assert fake_python_log == ""
