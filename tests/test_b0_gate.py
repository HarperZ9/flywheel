from pathlib import Path

from harness.b0_gate import extract_candidate, run_gate_for


def _seed(root: Path):
    fixture = root / "tasks" / "b0" / "add_one"
    fixture.mkdir(parents=True)
    (fixture / "hidden_test.py").write_text(
        "from solution import add_one as f\n"
        "def test_it():\n    assert f(1) == 2\n    assert f(-3) == -2\n",
        encoding="utf-8",
    )


def test_extract_candidate_strips_a_code_fence():
    fenced = "```python\ndef add_one(x):\n    return x + 1\n```"
    assert extract_candidate(fenced) == "def add_one(x):\n    return x + 1\n"


def test_extract_candidate_passes_bare_code_through():
    bare = "def add_one(x):\n    return x + 1\n"
    assert extract_candidate(bare) == bare


def test_correct_candidate_passes_the_gate(tmp_path):
    _seed(tmp_path)
    assert run_gate_for("add_one", "def add_one(x):\n    return x + 1\n", repo_root=tmp_path)


def test_wrong_candidate_fails_the_gate(tmp_path):
    _seed(tmp_path)
    assert not run_gate_for("add_one", "def add_one(x):\n    return x + 999\n", repo_root=tmp_path)


def test_missing_fixture_raises(tmp_path):
    _seed(tmp_path)
    try:
        run_gate_for("does_not_exist", "def f(): pass\n", repo_root=tmp_path)
    except FileNotFoundError:
        return
    raise AssertionError("expected FileNotFoundError for an unknown task id")
