"""PytestOracle falsifier: a skipped test is an assertion that never ran.

An all-skipped run exits 0 without executing one assertion, and a verifier
that cannot fail verifies nothing. Since 2026-09-23 the rule is stricter: any
skipped test makes the run FAIL, even beside a real pass. The report cannot
say who skipped, because a candidate can raise the same skip with the same
reason and location as a marker in the task's test file
(test_oracle_skip_escape.py measures that). A skip from the task's own
conftest.py FAILs for the same reason. A task that must not run a test
leaves it out of the recorded command, for example with --deselect.
"""
from harness.oracle import PytestOracle
from harness.task import Task

MIXED = ("import pytest\n\n"
         "@pytest.mark.skip(reason='guarded')\n"
         "def test_guarded():\n    assert False\n\n"
         "def test_real():\n    assert 1 + 1 == 2\n")


def _task(tmp_path, extra: str = "") -> Task:
    return Task(task_id="skip", prompt="p", oracle="pytest",
                oracle_cmd=f"python -m pytest tests/ -q{extra}", workdir=str(tmp_path),
                candidate_path="solution.py", max_new_tokens=8, retrieved=[])


def test_all_skipped_run_is_not_a_pass(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_skip.py").write_text(
        "import pytest\n\n"
        "@pytest.mark.skip(reason='guarded')\n"
        "def test_guarded():\n    assert False\n",
        encoding="utf-8")
    r = PytestOracle(timeout=60).verify("x = 1\n", task=_task(tmp_path))
    assert r.rc == 0          # pytest exits 0 on all-skip: that is the trap
    assert not r.passed       # the oracle refuses a run with zero executed assertions


def test_a_marker_skip_beside_a_real_pass_fails(tmp_path):
    """Before 2026-09-23 this run read PASS. The marker is the task's own, but
    its report entry is one a candidate can write too, so it cannot count."""
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_mixed.py").write_text(MIXED, encoding="utf-8")
    r = PytestOracle(timeout=60).verify("x = 1\n", task=_task(tmp_path))
    assert r.rc == 0
    assert not r.passed
    assert "skipped or xfailed" in r.stdout_excerpt


def test_a_conftest_skip_beside_a_real_pass_fails(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "conftest.py").write_text(
        "import pytest\n\n"
        "def pytest_runtest_setup(item):\n"
        "    if item.name == 'test_guarded':\n        pytest.skip('platform')\n",
        encoding="utf-8")
    (tmp_path / "tests" / "test_mixed.py").write_text(
        MIXED.replace("@pytest.mark.skip(reason='guarded')\n", ""), encoding="utf-8")
    r = PytestOracle(timeout=60).verify("x = 1\n", task=_task(tmp_path))
    assert r.rc == 0
    assert not r.passed
    assert "skipped or xfailed" in r.stdout_excerpt


def test_the_note_for_an_xfail_that_ran_does_not_say_it_never_ran(tmp_path):
    """A marker xfail runs its assertion. The run still FAILs, and the note
    that reaches the receipt must hold for an xfail as well as for a skip."""
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_known.py").write_text(
        MIXED.replace("skip(reason='guarded')", "xfail(reason='known')"),
        encoding="utf-8")
    r = PytestOracle(timeout=60).verify("x = 1\n", task=_task(tmp_path))
    assert r.rc == 0 and not r.passed
    assert "x." in r.stdout_excerpt   # pytest's progress marks: xfailed, passed
    assert "skipped or xfailed" in r.stdout_excerpt
    assert "never ran" not in r.stdout_excerpt


def test_a_deselected_test_beside_a_real_pass_passes(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_mixed.py").write_text(MIXED, encoding="utf-8")
    task = _task(tmp_path, " --deselect tests/test_mixed.py::test_guarded")
    r = PytestOracle(timeout=60).verify("x = 1\n", task=task)
    assert r.rc == 0
    assert r.passed           # the command names the exclusion; the witness re-runs it
