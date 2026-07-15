"""Acceptance-suite admission for arbitrary projects: the measured answer
to "can this suite refuse wrong code". One-operator mutants of the
project's own source must be KILLED by the suite; a survivor is named
with its exact mutation. The number every methodology assumes and none
measures. Sources are restored byte-exact whatever happens."""

import hashlib
from pathlib import Path

from harness.suite_audit import audit_suite

ADD_SRC = "def add(a, b):\n    return a + b\n"


def _project(tmp_path, test_body):
    (tmp_path / "solution.py").write_text(ADD_SRC, encoding="utf-8")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_solution.py").write_text(test_body, encoding="utf-8")
    return tmp_path


def test_strong_suite_kills_the_mutant(tmp_path):
    p = _project(tmp_path, "import sys\nsys.path.insert(0, '..')\n"
                 "from solution import add\n"
                 "def test_add(): assert add(2, 3) == 5\n")
    r = audit_suite(p)
    assert r["schema"] == "flywheel.suite-audit/v1"
    assert r["reference_ok"] is True
    assert r["attempted"] == 1 and r["killed"] == 1
    assert r["kill_rate"] == 1.0 and r["survivors"] == []


def test_hanging_mutant_is_indeterminate_not_killed(tmp_path):
    # The ' < ' -> ' <= ' flip turns this loop infinite: the run times out.
    # The hang ended the run, not the suite's assertions; crediting it as a
    # kill inflates the measured refusal floor.
    src = ("def clamp_steps(n):\n"
           "    i = 0\n"
           "    while i < n:\n"
           "        i = min(i+1, n)\n"
           "    return i\n")
    (tmp_path / "solution.py").write_text(src, encoding="utf-8")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_solution.py").write_text(
        "import sys\nsys.path.insert(0, '..')\n"
        "from solution import clamp_steps\n"
        "def test_clamp(): assert clamp_steps(3) == 3\n", encoding="utf-8")
    r = audit_suite(tmp_path, timeout=10)
    assert r["attempted"] == 1
    assert r["killed"] == 0                       # a hang is not a verdict
    assert r["kill_rate"] is None                 # zero decided mutants
    assert len(r["indeterminate"]) == 1
    assert r["indeterminate"][0]["outcome"] == "timeout"
    assert r["survivors"] == []
    assert r["restored"] is True


def test_weak_suite_survivor_is_named(tmp_path):
    p = _project(tmp_path, "import sys\nsys.path.insert(0, '..')\n"
                 "import solution\n"
                 "def test_imports(): assert solution is not None\n")
    r = audit_suite(p)
    assert r["kill_rate"] == 0.0
    s = r["survivors"][0]
    assert s["file"] == "solution.py"
    assert "a + b" in s["original"] and "a - b" in s["mutated"]


def test_broken_reference_refuses_to_audit(tmp_path):
    p = _project(tmp_path, "import sys\nsys.path.insert(0, '..')\n"
                 "from solution import add\n"
                 "def test_wrong(): assert add(2, 3) == 6\n")
    r = audit_suite(p)
    assert r["reference_ok"] is False
    assert r["attempted"] == 0
    assert "broken" in r["note"]


def test_sources_restored_byte_exact(tmp_path):
    p = _project(tmp_path, "import sys\nsys.path.insert(0, '..')\n"
                 "from solution import add\n"
                 "def test_add(): assert add(2, 3) == 5\n")
    before = hashlib.sha256(
        (p / "solution.py").read_bytes()).hexdigest()
    r = audit_suite(p)
    after = hashlib.sha256((p / "solution.py").read_bytes()).hexdigest()
    assert before == after
    assert r["restored"] is True
