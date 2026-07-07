"""self-validation: every expert reference solution must pass its OWN hidden tests.
A benchmark whose reference fails is broken. This does NOT test the model; it guards
the benchmark that will later measure the (currently unearned) uplift with headroom.
"""
import subprocess, sys, tempfile
from pathlib import Path
import pytest
from harness.tasks_expert import EXPERT_REGISTRY


def _run(spec, tmp):
    (tmp / "solution.py").write_text(spec.solution)
    td = tmp / "tests"; td.mkdir()
    (td / "test_it.py").write_text(spec.hidden_tests)
    r = subprocess.run([sys.executable, "-m", "pytest", str(td), "-q"],
                       cwd=tmp, capture_output=True, text=True)
    return r.returncode == 0, r.stdout


@pytest.mark.parametrize("spec", EXPERT_REGISTRY, ids=lambda s: s.task_id)
def test_reference_passes_own_hidden_tests(spec, tmp_path):
    ok, out = _run(spec, tmp_path)
    assert ok, f"{spec.task_id} reference FAILS its own tests -> broken benchmark:\n{out[-800:]}"


def test_registry_is_expert_and_nontrivial():
    assert len(EXPERT_REGISTRY) >= 7
    assert all(s.difficulty == "expert" for s in EXPERT_REGISTRY)
