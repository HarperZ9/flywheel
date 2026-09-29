"""The whole-suite CI job installs the lane packages the suite needs at their pins.

ci.yml once named ``index-graph==2.10.0`` by hand while the lane registry pinned
2.13.0. Nothing noticed until an auto-profile package older than its pin
stopped launching, and every test that launches the index lane failed on the
runner. ``scripts/ci_lane_pins.py`` reads the pin from the registry, so ci.yml
holds no second copy of it.
"""
from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pytest

from harness.lanes_registry import LANES

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "ci_lane_pins.py"
CI = ROOT / ".github" / "workflows" / "ci.yml"


def _module():
    spec = importlib.util.spec_from_file_location("ci_lane_pins", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _whole_suite_job() -> str:
    text = CI.read_text(encoding="utf-8")
    start = text.index("\n  full:")
    end = text.index("\n  gate:", start)
    return text[start:end]


def test_the_index_requirement_is_the_registry_pin():
    assert _module().requirement("index") == f"index-graph=={LANES['index'].version}"


def test_the_script_runs_on_a_bare_interpreter_from_the_repo_root():
    completed = subprocess.run(
        [sys.executable, "-S", str(SCRIPT), "index"], cwd=ROOT,
        capture_output=True, text=True, timeout=60)
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == f"index-graph=={LANES['index'].version}"


def test_a_lane_that_pip_cannot_install_is_refused():
    module = _module()
    with pytest.raises(ValueError, match="not a pip lane"):
        module.requirement("learn")
    assert module.main(["no-such-lane"]) == 2


def test_the_whole_suite_job_installs_index_from_the_registry():
    job = _whole_suite_job()
    assert "python scripts/ci_lane_pins.py index" in job
    assert re.search(r"index-graph\s*==", CI.read_text(encoding="utf-8")) is None, (
        "ci.yml names an index-graph version by hand; read it from the registry")
