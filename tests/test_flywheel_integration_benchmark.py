"""The spin step of the integration benchmark, run once and checked three ways.

Run 20260708_230923 passed a relative output root. The spin step changes the
working directory into <root>/spin, so every later use of the relative root
resolved under <root>/spin/<root>. The committed output repeated the run
root in paths up to 206 characters, and a Windows clone without core.longpaths
failed whenever the clone directory was longer than 51 characters. The fixture
below reproduces the cause: a relative root, entered from a temp dir.
"""
import os
from pathlib import Path

import pytest

from scripts.run_flywheel_integration_benchmark import run_spin_benchmark

RELATIVE_ROOT = Path("out") / "20260708_230923"
TASKS = ("fw_pass_a", "fw_pass_b", "fw_fail_a", "fw_fail_b")


@pytest.fixture(scope="module")
def spun(tmp_path_factory):
    # One run serves every test here: a spin pass shells out to pytest per
    # candidate and costs tens of seconds on a loaded Windows host.
    base = tmp_path_factory.mktemp("spin")
    before = Path.cwd()
    os.chdir(base)
    try:
        result = run_spin_benchmark(RELATIVE_ROOT, turns=1)
        after = Path.cwd()
    finally:
        os.chdir(before)
    written = sorted(p.relative_to(base).as_posix()
                     for p in base.rglob("*") if p.is_file())
    return {"base": base, "after": after, "result": result, "written": written}


def test_run_spin_benchmark_restores_original_cwd(spun):
    assert spun["result"]["schema"] == "flywheel.spin/integration/v1"
    assert spun["after"] == spun["base"]


def test_no_written_path_contains_the_run_root_twice(spun):
    root = RELATIVE_ROOT.as_posix()
    assert spun["written"], "the spin step wrote nothing, so the check is vacuous"
    nested = [p for p in spun["written"] if p.count(root) > 1]
    assert nested == [], f"output re-rooted under itself: {nested[:3]}"


def test_the_oracle_ran_where_the_tests_are(spun):
    # A positive control: the check above would also pass if the oracle wrote
    # its receipts somewhere else entirely. In the nested run every junit file
    # reported tests="0" and the pass rate was 0.0, not the 0.5 that two
    # correct candidates out of four earn.
    root = RELATIVE_ROOT.as_posix()
    for task in TASKS:
        assert f"{root}/spin/{task}/_oracle_junit.xml" in spun["written"]
    assert spun["result"]["first_turn"]["pass_rate"] == 0.5
