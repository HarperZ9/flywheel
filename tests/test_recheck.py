"""Recheck manifests stay well formed, and the runner fails closed.

The manifests in recheck/ are what a stranger runs, so each one must load, name
a full commit and a control, and pass the schema check. The runner tests use a
manifest pinned to this checkout's HEAD with a trivial command, so they need no
network: one where command and control behave as declared (PASS), one whose
control does not fail (FAIL, since a check never shown to fail proves nothing),
and one whose expected output is absent (FAIL).

The runner tests point the runner at a one-file repository, so each worktree is
one file. A full checkout of this repository is about 8,000 files, and on a busy
Windows runner adding and removing it once outran the 60 second test timeout.
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


@pytest.fixture
def tiny_repo(tmp_path, monkeypatch):
    """A one-commit repository holding only pyproject.toml, used as the runner's REPO."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_bytes(b"[project]\nname = 'tiny'\n")
    try:
        for args in (["init", "-q"], ["add", "pyproject.toml"],
                     ["-c", "user.name=t", "-c", "user.email=t@example.invalid",
                      "commit", "-q", "-m", "tiny"]):
            subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("git is not available")
    monkeypatch.setattr(recheck, "REPO", repo)
    return repo


def _head(repo: Path) -> str:
    return subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True,
                          text=True, check=True).stdout.strip()


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


def test_runner_passes_when_command_and_control_behave(tmp_path, tiny_repo):
    work = tmp_path / "work"
    work.mkdir()
    m = _local(_head(tiny_repo))
    result = recheck.recheck(m, work)
    assert result["ok"], result
    assert not (work / "checkout").exists(), "the worktree must be removed"


def test_runner_fails_when_the_control_does_not_fail(tmp_path, tiny_repo):
    m = _local(_head(tiny_repo))
    m["control"]["mutate"]["replace"] = "[project]"
    work = tmp_path / "work"
    work.mkdir()
    result = recheck.recheck(m, work)
    assert not result["ok"] and result["control"]["misses"]


def test_runner_fails_when_expected_output_is_missing(tmp_path, tiny_repo):
    m = _local(_head(tiny_repo))
    m["expect"]["stdout_contains"] = ["not printed"]
    work = tmp_path / "work"
    work.mkdir()
    result = recheck.recheck(m, work)
    assert not result["ok"] and result["main"]["misses"]


def test_a_missing_declared_package_stops_the_run_before_any_verdict(tmp_path, tiny_repo):
    m = _local(_head(tiny_repo))
    m["needs"]["packages"] = ["no_such_module_for_recheck"]
    work = tmp_path / "work"
    work.mkdir()
    with pytest.raises(RuntimeError, match="no_such_module_for_recheck"):
        recheck.recheck(m, work)
    assert not (work / "checkout").exists()


def test_a_stuck_worktree_remove_is_bounded_and_the_checkout_still_goes(tmp_path, tiny_repo, monkeypatch):
    """When `git worktree remove` does not return, the runner stops waiting,
    deletes the folder itself and prunes the worktree record."""
    work = tmp_path / "work"
    work.mkdir()
    real_git = recheck._git
    seen = {}

    def git(*args, **kw):
        if "remove" in args:
            seen["timeout"] = kw.get("timeout")
            raise subprocess.TimeoutExpired(["git", *args], kw.get("timeout") or 0)
        return real_git(*args, **kw)

    monkeypatch.setattr(recheck, "_git", git)
    result = recheck.recheck(_local(_head(tiny_repo)), work)
    assert result["ok"], result
    assert seen["timeout"] and seen["timeout"] <= recheck.REMOVE_SECONDS
    assert not (work / "checkout").exists(), "the folder must go even when git hangs"
    listed = subprocess.run(["git", "-C", str(tiny_repo), "worktree", "list", "--porcelain"],
                            capture_output=True, text=True, check=True).stdout
    assert "checkout" not in listed, "the worktree record must be pruned"
