"""Retention is a release boundary, not evidence of fairness or semantic quality."""
import json
import re
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/check_release_ruleset.py"
BASELINE = ROOT / "scripts/release_ruleset_baseline.json"
MODULES = ("__init__", "detector", "masking", "profiles", "genres", "modes")


@pytest.fixture
def candidate(tmp_path):
    package = tmp_path / "src/articulate"
    package.mkdir(parents=True)
    for name in MODULES:
        shutil.copyfile(ROOT / f"src/articulate/{name}.py", package / f"{name}.py")
    return tmp_path


def run_gate(root, baseline=BASELINE):
    assert SCRIPT.exists(), "release ruleset retention gate is missing"
    result = subprocess.run(
        [sys.executable, "-I", "-S", str(SCRIPT), "--root", str(root),
         "--baseline", str(baseline)], capture_output=True, text=True, timeout=30)
    return result, json.loads(result.stdout)


def test_retained_release_detector_is_accepted(candidate):
    result, receipt = run_gate(candidate)
    assert result.returncode == 0, receipt
    assert receipt["status"] == "PASS"
    assert receipt["baseline_commit"] == "2884ce4a489b6598d51b57bbdfc98edb3d3ef306"
    assert receipt["checked_files"] == 6
    assert "reviewed baseline" in receipt["scope"]


@pytest.mark.parametrize("name", MODULES)
def test_changed_behavior_file_is_refused(candidate, name):
    path = candidate / f"src/articulate/{name}.py"
    path.write_text(path.read_text(encoding="utf-8") + "\nraise RuntimeError('mutation')\n",
                    encoding="utf-8")
    result, receipt = run_gate(candidate)
    assert result.returncode == 1
    assert any(f"{name}.py" in reason for reason in receipt["failures"])


def test_missing_file_is_refused(candidate):
    (candidate / "src/articulate/masking.py").unlink()
    result, receipt = run_gate(candidate)
    assert result.returncode == 1
    assert receipt["status"] == "FAIL"


def test_baseline_cannot_be_refreshed_to_accept_changed_rules(candidate, tmp_path):
    altered = json.loads(BASELINE.read_text(encoding="utf-8"))
    altered["ruleset_fingerprint"] = "sha256:0000000000000000"
    fake = tmp_path / "fake-baseline.json"
    fake.write_text(json.dumps(altered), encoding="utf-8")
    result, receipt = run_gate(candidate, fake)
    assert result.returncode == 1
    assert "baseline digest" in " ".join(receipt["failures"])


def test_package_shadowing_is_refused(candidate):
    shadow = candidate / "src/articulate/detector"
    shadow.mkdir()
    (shadow / "__init__.py").write_text("def check_text(*a, **k): return {}\n")
    result, receipt = run_gate(candidate)
    assert result.returncode == 1
    assert "shadow" in " ".join(receipt["failures"])


def test_only_initializer_version_metadata_may_change(candidate):
    init = candidate / "src/articulate/__init__.py"
    init.write_text(re.sub(r'(?m)^__version__ = "[^"]+"$', '__version__ = "99.0.0"',
                           init.read_text(encoding="utf-8")),
                    encoding="utf-8")
    result, receipt = run_gate(candidate)
    assert result.returncode == 0, receipt


def test_editor_guards_are_outside_detector_retention_scope(candidate):
    (candidate / "src/articulate/meaning_guard.py").write_text(
        "raise RuntimeError('must not execute editor while checking rules')\n")
    result, receipt = run_gate(candidate)
    assert result.returncode == 0, receipt


def test_crlf_checkout_is_equivalent(candidate):
    path = candidate / "src/articulate/masking.py"
    path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    result, receipt = run_gate(candidate)
    assert result.returncode == 0, receipt
