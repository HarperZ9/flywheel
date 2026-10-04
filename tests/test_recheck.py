"""Recheck manifests stay well formed, and the runner fails closed.

The manifests in recheck/ are what a stranger runs, so each one must load, name
a full commit and a control, and pass the schema check. The runner tests use a
manifest pinned to this checkout's HEAD with a trivial command, so they need no
network: one where command and control behave as declared (PASS), one whose
control does not fail (FAIL, since a check never shown to fail proves nothing),
and one whose expected output is absent (FAIL).
"""
import copy
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from harness import recheck, recheck_manifest as rm  # noqa: E402

MANIFESTS = rm.discover(ROOT)


def test_there_are_manifests_and_cpu_ones_run_in_ci():
    loaded = [rm.load(p) for p in MANIFESTS]
    assert len(loaded) >= 6
    assert sum(m["needs"]["hardware"] == "cpu" and m["ci"] is True for m in loaded) >= 6


@pytest.mark.parametrize("path", MANIFESTS, ids=lambda p: p.stem)
def test_manifest_is_well_formed(path):
    m = rm.load(path)
    assert m["id"] == path.stem
    assert m["control"]["expect"] != m["expect"], "the control must expect a different outcome"


def _base() -> dict:
    return rm.load(ROOT / "recheck" / "pysyft-result-receipt.json")


@pytest.mark.parametrize("field,value,needle", [
    ("commit", "abc123", "full 40-character SHA"),
    ("level", "vibes", "level must be one of"),
    ("ci", False, "ci_skip_reason"),
    ("repository", "github.com/x", "full https URL"),
])
def test_schema_names_each_problem(field, value, needle):
    m = _base()
    m[field] = value
    assert any(needle in p for p in rm.problems_in(m))


def test_a_control_without_a_description_is_refused():
    m = _base()
    m["control"] = {"expect": {"exit_code": 1}}
    assert any("never shown to fail" in p for p in rm.problems_in(m))


def _head() -> str:
    try:
        return subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True,
                              text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("not a git checkout")


def _local(head: str) -> dict:
    m = copy.deepcopy(_base())
    m.update(id="local", commit=head, cwd="checkout", inputs=[], setup=[],
             command=["{python}", "-c",
                      "import pathlib; print('[project]' in pathlib.Path('pyproject.toml').read_text())"],
             expect={"exit_code": 0, "stdout_contains": ["True"]})
    m["control"] = {"description": "break the first line",
                    "mutate": {"file": "{checkout}/pyproject.toml", "find": "[project]", "replace": "[broken]"},
                    "expect": {"exit_code": 0, "stdout_lacks": ["True"]}}
    return m


def test_runner_passes_when_command_and_control_behave(tmp_path):
    m = _local(_head())
    result = recheck.recheck(m, tmp_path)
    assert result["ok"], result
    assert not (tmp_path / "checkout").exists(), "the worktree must be removed"


def test_runner_fails_when_the_control_does_not_fail(tmp_path):
    m = _local(_head())
    m["control"]["mutate"]["replace"] = "[project]"
    result = recheck.recheck(m, tmp_path)
    assert not result["ok"] and result["control"]["misses"]


def test_runner_fails_when_expected_output_is_missing(tmp_path):
    m = _local(_head())
    m["expect"]["stdout_contains"] = ["not printed"]
    result = recheck.recheck(m, tmp_path)
    assert not result["ok"] and result["main"]["misses"]


def test_a_missing_declared_package_stops_the_run_before_any_verdict(tmp_path):
    m = _local(_head())
    m["needs"]["packages"] = ["no_such_module_for_recheck"]
    with pytest.raises(RuntimeError, match="no_such_module_for_recheck"):
        recheck.recheck(m, tmp_path)
    assert not (tmp_path / "checkout").exists()
