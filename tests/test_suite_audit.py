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
