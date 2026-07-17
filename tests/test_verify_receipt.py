"""test_verify_receipt.py — re-checking a receipt reproduces (or exposes) the verdict.

Success criteria:
  - MATCH when the re-run reproduces verdict + output hash; DRIFT on either mismatch.
  - end to end with real pytest: a genuine receipt re-verifies MATCH.
"""
from harness.envelope import ProofEnvelope
from harness.oracle import OracleResult, PytestOracle
from harness.task import Task
from harness.verify_receipt import verify_envelope


class _FixedOracle:
    oracle_type = "fixed"

    def __init__(self, passed, output_hash):
        self._passed, self._hash = passed, output_hash

    def verify(self, candidate, task):
        return OracleResult(self._passed, "cmd", self._hash, "", 0 if self._passed else 1)


def _env(verdict="PASS", output_hash="abc"):
    return ProofEnvelope(task_id="t", candidate="def f(): return 1", oracle="pytest",
                         oracle_cmd="pytest", oracle_output_hash=output_hash, verdict=verdict,
                         model_ref="m", seed=0, prompt_hash="p", budget_spent={})


def _task():
    return Task(task_id="t", prompt="p", oracle="pytest", oracle_cmd="pytest",
                workdir=".", candidate_path="s.py")


def test_match_when_reproduced():
    r = verify_envelope(_env("PASS", "abc"), _task(), oracle=_FixedOracle(True, "abc"))
    assert r["verdict"] == "MATCH"


def test_drift_on_output_hash():
    r = verify_envelope(_env("PASS", "abc"), _task(), oracle=_FixedOracle(True, "xyz"))
    assert r["verdict"] == "DRIFT" and r["checks"]["output_hash_matches"] is False


def test_drift_on_verdict():
    r = verify_envelope(_env("PASS", "abc"), _task(), oracle=_FixedOracle(False, "abc"))
    assert r["verdict"] == "DRIFT" and r["checks"]["verdict_matches"] is False


def test_end_to_end_real_receipt_re_verifies(tmp_path):
    (tmp_path / "test_s.py").write_text(
        "from s import f\ndef test_f():\n    assert f() == 1\n", encoding="utf-8")
    task = Task(task_id="t", prompt="p", oracle="pytest",
                oracle_cmd="python -m pytest test_s.py", workdir=str(tmp_path),
                candidate_path="s.py")
    candidate = "def f():\n    return 1\n"
    real = PytestOracle().verify(candidate, task)          # produce a genuine result
    env = ProofEnvelope(task_id="t", candidate=candidate, oracle="pytest",
                        oracle_cmd=task.oracle_cmd, oracle_output_hash=real.output_hash,
                        verdict=real.verdict(), model_ref="m", seed=0, prompt_hash="p",
                        budget_spent={})
    assert verify_envelope(env, task)["verdict"] == "MATCH"   # re-runs real pytest
