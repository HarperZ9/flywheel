"""Control for the report-only `test diff` job in flywheel CI.

The job runs `articulate code test-diff BASE HEAD` on every pull request. This
file plants the three things the job exists to flag (a deleted check, a new
skip, a check that cannot fail) in a throwaway git repository and holds that
the command line reports each by rule. It also holds the other side: a change
that only adds a real check reports clean, so the planted case is not caught
by a checker that flags everything.
"""
import json
import subprocess

import pytest

from articulate.cli import main

HONEST = '''\
def add(a, b):
    return a + b


def test_add():
    assert add(2, 2) == 4
    assert add(-1, 1) == 0


def test_other():
    assert add(1, 1) == 2
'''

WEAKENED = '''\
import pytest


def add(a, b):
    return a + b


def test_add():
    assert add(2, 2)


@pytest.mark.skip
def test_other():
    assert add(1, 1) == 2


def test_new():
    assert True
'''

STRONGER = HONEST + '''

def test_zero():
    assert add(0, 0) == 0
'''


def _git(repo, *args):
    done = subprocess.run(["git", "-C", str(repo), "-c", "user.email=ci@example.invalid",
                           "-c", "user.name=ci", "-c", "core.autocrlf=false", *args],
                          capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stderr
    return done.stdout.strip()


def _repo(tmp_path, second):
    repo = tmp_path / "repo"
    (repo / "tests").mkdir(parents=True)
    _git(repo, "init", "-q")
    target = repo / "tests" / "test_sum.py"
    target.write_text(HONEST, encoding="utf-8", newline="\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "honest tests")
    base = _git(repo, "rev-parse", "HEAD")
    target.write_text(second, encoding="utf-8", newline="\n")
    _git(repo, "commit", "-q", "-a", "-m", "second")
    return repo, base, _git(repo, "rev-parse", "HEAD")


def _report(capsys, repo, base, head):
    code = main(["code", "test-diff", base, head, "--repo", str(repo), "--json"])
    return code, json.loads(capsys.readouterr().out)


def test_planted_weakened_test_is_reported_by_rule(tmp_path, capsys):
    repo, base, head = _repo(tmp_path, WEAKENED)
    code, report = _report(capsys, repo, base, head)
    assert code == 0, "report-only: findings never change the exit status"
    assert report["status"] == "findings"
    found = {(row["rule"], row["test"]) for row in report["findings"]
             if row["tier"] == "finding"}
    assert ("assertion-deleted", "test_add") in found
    assert ("skip-added", "test_other") in found
    assert ("assert-true", "test_new") in found
    assert report["counts"]["finding"] == len(found) == 3


def test_change_that_only_adds_a_real_check_is_clean(tmp_path, capsys):
    repo, base, head = _repo(tmp_path, STRONGER)
    code, report = _report(capsys, repo, base, head)
    assert code == 0
    assert report["status"] == "clean"
    assert report["findings"] == []


def test_unknown_commit_is_an_error_not_a_clean_report(tmp_path, capsys):
    repo, base, _ = _repo(tmp_path, STRONGER)
    code = main(["code", "test-diff", base, "0" * 40, "--repo", str(repo), "--json"])
    captured = capsys.readouterr()
    assert code == 2
    assert captured.out == ""
    assert "articulate code:" in captured.err


def test_code_is_listed_in_help(capsys):
    with pytest.raises(SystemExit) as stop:
        main(["--help"])
    assert stop.value.code == 0
    assert "code" in capsys.readouterr().out.split("positional arguments:")[1]
