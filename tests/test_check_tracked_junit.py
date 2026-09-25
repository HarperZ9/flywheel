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
BODY = DIRTY[len(HEAD):]   # the dirty report without its XML declaration


def _report(failure: bytes) -> bytes:
    """A report with no host whose one failure holds `failure` as text."""
    return HEAD + (b'<testsuites><testsuite hostname=""><testcase name="a">'
                   b"<failure>" + failure + b"</failure></testcase>"
                   b"</testsuite></testsuites>")


def _utf16(data: bytes, bom: bytes = b"\xff\xfe") -> bytes:
    codec = "utf-16-be" if bom == b"\xfe\xff" else "utf-16-le"
    return bom + data.decode("utf-8").encode(codec)


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
    b"/c/Users/someone/proj/tests/test_x.py",        # MSYS2 and Git Bash
    b"/cygdrive/c/Users/someone/proj/test_x.py",     # Cygwin
    b"/workspaces/flywheel/tests/test_x.py",         # Codespaces
    b"/__w/flywheel/flywheel/tests/test_x.py",       # Actions container job
    b"/data/someone/proj/test_x.py",
])
def test_posix_and_unc_paths_are_found(path):
    body = _report(path + b":3: AssertionError")
    assert any(f.startswith("absolute path") for f in findings(body))


@pytest.mark.parametrize("attr", [
    b'hostname="build-host-01"', b"hostname='build-host-01'",
    b'hostname = "build-host-01"', b'hostname\n="build-host-01"',
    b'hostname=\t"build-host-01"',
])
def test_every_xml_spelling_of_the_hostname_attribute_is_found(attr):
    body = HEAD + b'<testsuites><testsuite name="pytest" ' + attr \
        + b' tests="1"><testcase name="a" /></testsuite></testsuites>'
    assert findings(body) == ["hostname build-host-01"]


def test_the_hostname_rule_reads_attributes_not_failure_text():
    # A test may assert on its own hostname fixture. That is test data, not
    # the machine the report was written on, which pytest puts in the attribute.
    assert findings(_report(b"assert connect(hostname='db') is None")) == []
    later = HEAD + (b'<testsuites><testsuite name="a &gt; b" message="x > y" '
                    b'hostname="build-host-01" /></testsuites>')
    assert findings(later) == ["hostname build-host-01"]


def test_a_report_with_no_host_and_relative_paths_is_clean():
    # '/a/b' and '/h/p?a' are URL path literals from a real uplift task. A
    # one-letter segment reads as an MSYS2 drive only with two more segments.
    rel = _report(b"tests/test_x.py:3: E  assert 1 == 2 (see "
                  b"http://example.test/a) and split('/h/p?a') == '/a/b'")
    assert findings(CLEAN) == []
    assert findings(rel) == []


@pytest.mark.parametrize("literal", [
    b"assert path == '/tmp/cache'",
    b"assert parse('/usr/bin/env python') == 'python'",
    b"assert split('k:\\\\tv') == ['k', 'v']",
])
def test_a_path_shaped_literal_fails_even_from_test_source(literal):
    # The documented contract errs toward failing: the gate cannot tell a
    # literal in a test's own source from a path on the build machine.
    assert any(f.startswith("absolute path") for f in findings(_report(literal)))


def test_a_utf16_report_is_read_as_text():
    for data in (_utf16(DIRTY), _utf16(DIRTY, b"\xfe\xff")):
        found = findings(data)
        assert "hostname build-host-01" in found
        assert any(f.startswith("absolute path C:\\Users\\someone") for f in found)


def test_reports_are_found_by_name_and_by_content():
    assert is_junit_report("a/_oracle_junit.xml", b"")
    assert is_junit_report("a/_oracle_junit_0123456789abcdef.xml", b"")
    assert is_junit_report("out/results.xml", CLEAN)
    assert is_junit_report("out/bom.xml", b"\xef\xbb\xbf" + CLEAN)
    manifest = HEAD + b'<manifest package="x"><application/></manifest>'
    assert not is_junit_report("app/AndroidManifest.xml", manifest)


REPORTS = {   # path -> bytes that are a JUnit report
    "out/RESULTS.XML": CLEAN,
    "out/junit-report.out": CLEAN,
    "out/pytest.junit": CLEAN,
    "notes/junit.txt": CLEAN,
    "out/doctype.xml": HEAD + b"\n<!DOCTYPE testsuites>\n" + BODY,
    "out/doctype-subset.xml": b'<!DOCTYPE testsuites [ <!ENTITY a "b"> ]>' + BODY,
    "out/styled.xml": HEAD + b'<?xml-stylesheet type="text/xsl" href="j.xsl"?>'
                      b"\n<!-- run 1 - of 2 -->\n" + BODY,
    "out/utf16le.xml": _utf16(CLEAN),
    "out/utf16be.xml": _utf16(CLEAN, b"\xfe\xff"),
    "out/utf16-no-bom.xml": _utf16(CLEAN, b""),
}
QUOTES = {    # path -> bytes that hold a report's text but are not one
    "tests/test_x.py": b"BODY = '''" + CLEAN + b"'''\n",
    "docs/junit.md": b"```xml\n" + CLEAN + b"\n```\n",
    "out/comment.xml": HEAD + b"<!-- <testsuites> --><manifest />",
    "img/logo.png": b"\x89PNG\r\n\x1a\n" + b"\x00" * 16,
}


@pytest.mark.parametrize("path", list(REPORTS))
def test_a_report_is_found_whatever_its_name_prolog_or_encoding(path):
    assert is_junit_report(path, REPORTS[path])


@pytest.mark.parametrize("path", list(QUOTES))
def test_text_that_only_quotes_a_report_is_not_one(path):
    assert not is_junit_report(path, QUOTES[path])


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


def test_the_gate_bites_on_a_report_under_any_name_or_encoding(tmp_path, capsys):
    odd = {
        "out/RESULTS.XML": DIRTY,
        "out/pytest.junit": DIRTY,
        "out/doctype.xml": HEAD + b"<!DOCTYPE testsuites>" + BODY,
        "out/utf16.xml": _utf16(DIRTY),
    }
    _git(tmp_path, "init", "-q")
    _track(tmp_path, "README.md", b"x\n")
    for path, data in odd.items():
        _track(tmp_path, path, data)
    assert main(tmp_path) == 1
    out = capsys.readouterr().out
    for path in odd:
        assert f"{path}: hostname build-host-01" in out
    assert "4 of 4 tracked JUnit reports" in out


def test_a_tree_with_no_reports_is_clean(tmp_path, capsys):
    _git(tmp_path, "init", "-q")
    _track(tmp_path, "README.md", b"x\n")
    assert main(tmp_path) == 0
    assert "0 tracked JUnit reports" in capsys.readouterr().out


def test_a_tree_that_tracks_nothing_is_an_error_not_a_pass(tmp_path, capsys):
    # An empty index is what a broken or half-made checkout looks like. A
    # gate that read it as "0 reports, clean" would pass without checking.
    _git(tmp_path, "init", "-q")
    assert main(tmp_path) == 2
    assert "no tracked files" in capsys.readouterr().out


def test_a_blob_git_cannot_read_is_an_error_not_a_pass(tmp_path, capsys):
    _git(tmp_path, "init", "-q")
    _track(tmp_path, "README.md", b"x\n")
    _git(tmp_path, "update-index", "--add", "--cacheinfo",
         "100644," + "1" * 40 + ",out/results.xml")
    assert main(tmp_path) == 2
    assert "could not read" in capsys.readouterr().out


def test_no_git_checkout_is_an_error_not_a_pass(tmp_path, monkeypatch):
    # Stop git from finding a repository above tmp_path.
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    assert main(tmp_path) == 2
