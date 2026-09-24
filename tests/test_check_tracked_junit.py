"""The tracked JUnit report gate: the rule, the real tree, the ignore rules, a bite."""
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from check_tracked_junit import findings, is_junit_report, main  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
# Synthetic values throughout: no real host or user name appears here.
HEAD = b'<?xml version="1.0" encoding="utf-8"?>'
DIRTY = HEAD + (b'<testsuites><testsuite name="pytest" hostname="build-host-01">'
                b'<testcase classname="t" name="a"><error message="x">'
                b'C:\\Users\\someone\\proj\\tests\\test_x.py:1: ImportError'
                b'</error></testcase></testsuite></testsuites>')
CLEAN = HEAD + (b'<testsuites><testsuite name="pytest" hostname="">'
                b'<testcase classname="tests.test_x" name="a" />'
                b'</testsuite></testsuites>')


def _git(repo: Path, *args: str, stdin: bytes | None = None) -> bytes:
    proc = subprocess.run(["git", "-C", str(repo), *args], input=stdin,
                          capture_output=True)
    assert proc.returncode == 0, proc.stderr.decode("utf-8", errors="replace")
    return proc.stdout


def _track(repo: Path, path: str, data: bytes) -> None:
    # Index only, as in the path-length gate test: the gate reads what git
    # tracks, not what happens to sit on disk.
    blob = _git(repo, "hash-object", "-w", "--stdin", stdin=data).decode().strip()
    _git(repo, "update-index", "--add", "--cacheinfo", f"100644,{blob},{path}")


def test_a_hostname_and_a_drive_path_are_both_named():
    found = findings(DIRTY)
    assert "hostname build-host-01" in found
    assert any(f.startswith("absolute path C:\\Users\\someone") for f in found)


@pytest.mark.parametrize("path", [
    b"/home/someone/proj/tests/test_x.py",
    b"/Users/someone/proj/tests/test_x.py",
    b"/tmp/pytest-of-someone/pytest-1/test_x.py",
    b"\\\\fileserver\\share\\proj\\test_x.py",
    b"file:///home/someone/proj/test_x.py",
])
def test_posix_and_unc_paths_are_found(path):
    body = HEAD + b'<testsuites><testsuite hostname=""><testcase name="a">' \
        + b"<failure>" + path + b":3: AssertionError</failure></testcase>" \
        + b"</testsuite></testsuites>"
    assert any(f.startswith("absolute path") for f in findings(body))


def test_a_report_with_no_host_and_relative_paths_is_clean():
    rel = HEAD + (b'<testsuites><testsuite hostname=""><testcase name="a">'
                  b"<failure>tests/test_x.py:3: E  assert 1 == 2 (see "
                  b"http://example.test/a)</failure></testcase>"
                  b"</testsuite></testsuites>")
    assert findings(CLEAN) == []
    assert findings(rel) == []


def test_reports_are_found_by_name_and_by_content():
    assert is_junit_report("a/_oracle_junit.xml", b"")
    assert is_junit_report("a/_oracle_junit_0123456789abcdef.xml", b"")
    assert is_junit_report("out/results.xml", CLEAN)
    assert is_junit_report("out/bom.xml", b"\xef\xbb\xbf" + CLEAN)
    manifest = HEAD + b'<manifest package="x"><application/></manifest>'
    assert not is_junit_report("app/AndroidManifest.xml", manifest)
    assert not is_junit_report("notes/junit.txt", CLEAN)


@pytest.mark.parametrize("name", [
    "_oracle_junit.xml", "_oracle_junit_0123456789abcdef.xml",
    "_oracle_junit.json", "oracle_junit.xml", "x_oracle_junit.xml",
])
def test_the_name_rule_matches_the_harness(name):
    # The gate runs on a bare interpreter from scripts/, so it copies the
    # prefix rather than importing harness. This pins the copy to the source.
    from harness.junit_report import is_report_name
    assert is_junit_report(f"w/{name}", b"") == is_report_name(name)


def test_the_real_tree_passes():
    if not (ROOT / ".git").exists():
        pytest.skip("not a git checkout, so there is no tracked tree to check")
    assert main(ROOT) == 0


@pytest.mark.parametrize("path", [
    "_oracle_junit.xml",
    "tasks/example_pass/workdir/_oracle_junit.xml",
    "artifacts/uplift/work_x/task/_oracle_junit_0123456789abcdef.xml",
])
def test_the_repo_ignores_canonical_and_per_run_reports(path):
    if not (ROOT / ".git").exists():
        pytest.skip("not a git checkout, so there is no ignore file to read")
    # -v names the rule that matched. It has to be the committed .gitignore:
    # a global excludes file or .git/info/exclude would pass this on one
    # machine and not on a fresh clone.
    proc = subprocess.run(["git", "-C", str(ROOT), "check-ignore", "-v",
                           "--no-index", path], capture_output=True, text=True)
    assert proc.returncode == 0, f"{path} is not ignored"
    assert proc.stdout.startswith(".gitignore:"), proc.stdout


def test_the_gate_bites_on_a_tracked_report_that_names_a_host(tmp_path, capsys):
    _git(tmp_path, "init", "-q")
    _track(tmp_path, "README.md", b"x\n")
    _track(tmp_path, "run/w/_oracle_junit.xml", DIRTY)
    _track(tmp_path, "run/w/results.xml", DIRTY)
    _track(tmp_path, "run/ok/_oracle_junit.xml", CLEAN)
    assert main(tmp_path) == 1
    out = capsys.readouterr().out
    assert "run/w/_oracle_junit.xml: hostname build-host-01" in out
    assert "run/w/results.xml: hostname build-host-01" in out
    assert "run/ok/" not in out


def test_a_tree_with_no_reports_is_clean(tmp_path, capsys):
    _git(tmp_path, "init", "-q")
    _track(tmp_path, "README.md", b"x\n")
    assert main(tmp_path) == 0
    assert "0 tracked JUnit reports" in capsys.readouterr().out


def test_no_git_checkout_is_an_error_not_a_pass(tmp_path, monkeypatch):
    # Stop git from finding a repository above tmp_path.
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    assert main(tmp_path) == 2
