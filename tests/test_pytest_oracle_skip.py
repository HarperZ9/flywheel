"""PytestOracle falsifier: an all-skipped run exits 0 without executing one
assertion. A verifier that cannot fail verifies nothing; the oracle must
demand at least one test that actually PASSED, not a green exit code."""
from harness.oracle import PytestOracle
from harness.task import Task


def _task(tmp_path) -> Task:
    return Task(task_id="skip", prompt="p", oracle="pytest",
                oracle_cmd="python -m pytest tests/ -q", workdir=str(tmp_path),
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


def test_one_real_pass_beside_skips_still_passes(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_mixed.py").write_text(
        "import pytest\n\n"
        "@pytest.mark.skip(reason='guarded')\n"
        "def test_guarded():\n    assert False\n\n"
        "def test_real():\n    assert 1 + 1 == 2\n",
        encoding="utf-8")
    r = PytestOracle(timeout=60).verify("x = 1\n", task=_task(tmp_path))
    assert r.rc == 0
    assert r.passed
