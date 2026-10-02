"""The red check: new tests run against the parent commit and each result is
sorted by cause. Each case builds a two-commit repository, so the classes below
come from real pytest runs, not from canned reports."""
import subprocess
import textwrap

import pytest

from harness.red_check import provenance, red_check
from harness.red_classify import classify_failure, parse_junit
from harness.red_select import changed_tests

BUGGY = "def add(a, b):\n    return a - b\n"
FIXED = "def add(a, b):\n    return a + b\n"


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _repo(tmp_path, base_files, head_files):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.invalid")
    _git(repo, "config", "user.name", "t")
    _git(repo, "config", "core.autocrlf", "false")
    for files in (base_files, head_files):
        for path, text in files.items():
            target = repo / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(textwrap.dedent(text), encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", "step")
    return repo


def _classes(receipt):
    return {row["test"].split("::")[-1]: row["class"] for row in receipt["tests"]}


@pytest.fixture
def fixed_bug(tmp_path):
    head_test = """
        from calc import add

        def test_adds():
            assert add(2, 3) == 5

        def test_only_runs():
            assert add(2, 3) is not None

        def test_skips():
            import pytest
            pytest.skip("not today")
    """
    return _repo(tmp_path, {"calc.py": BUGGY, "tests/test_calc.py": "def test_old():\n    pass\n"},
                 {"calc.py": FIXED, "tests/test_calc.py": head_test})


def test_a_bug_fix_test_is_red_on_an_assertion_and_a_weak_one_is_green(fixed_bug):
    receipt = red_check(fixed_bug, "HEAD~1", "HEAD")
    assert receipt["schema"] == "flywheel.red-check/v1"
    assert _classes(receipt) == {"test_adds": "red-assert", "test_only_runs": "green",
                                 "test_skips": "indeterminate"}
    assert receipt["credited"] == 1
    assert receipt["provenance"]["status"] == "ok"
    assert receipt["does_not_prove"]


def test_a_skip_on_both_sides_is_never_credited(fixed_bug):
    row = next(r for r in red_check(fixed_bug, "HEAD~1", "HEAD")["tests"]
               if r["test"].endswith("test_skips"))
    # skipped at head, so the head control refuses it before any base credit
    assert row["head"] == "skipped" and row["base_runs"] == ["skipped", "skipped"]


def test_a_new_feature_test_is_red_only_because_the_symbol_is_missing(tmp_path):
    repo = _repo(tmp_path, {"calc.py": FIXED, "tests/test_calc.py": "def test_old():\n    pass\n"},
                 {"calc.py": FIXED + "\ndef mul(a, b):\n    return a * b\n",
                  "tests/test_calc.py": "from calc import mul\n\ndef test_mul():\n"
                                        "    assert mul(2, 3) == 6\n"})
    receipt = red_check(repo, "HEAD~1", "HEAD")
    assert _classes(receipt) == {"test_mul": "red-missing-symbol"}
    assert receipt["credited"] == 0


def test_a_test_that_fails_at_head_too_is_indeterminate(tmp_path):
    repo = _repo(tmp_path, {"calc.py": BUGGY},
                 {"calc.py": FIXED, "tests/test_calc.py":
                  "from calc import add\n\ndef test_wrong():\n    assert add(2, 3) == 7\n"})
    row = red_check(repo, "HEAD~1", "HEAD")["tests"][0]
    assert row["class"] == "indeterminate" and row["head"] == "red-assert"


def test_a_flaky_test_is_indeterminate(tmp_path):
    flaky = """
        import pathlib
        from calc import add

        def test_flips():
            mark = pathlib.Path(__file__).with_name("seen")
            first = not mark.exists()
            mark.write_text("x")
            assert first or add(2, 3) == 5
    """
    repo = _repo(tmp_path, {"calc.py": BUGGY}, {"calc.py": FIXED, "tests/test_calc.py": flaky})
    row = red_check(repo, "HEAD~1", "HEAD", check_head=False)["tests"][0]
    assert row["base_runs"] == ["green", "red-assert"]
    assert row["class"] == "indeterminate" and row["detail"].startswith("flaky")


def test_an_error_inside_the_code_is_not_an_assertion_failure(tmp_path):
    repo = _repo(tmp_path, {"calc.py": "def add(a, b):\n    return a + None\n"},
                 {"calc.py": FIXED, "tests/test_calc.py":
                  "from calc import add\n\ndef test_adds():\n    assert add(2, 3) == 5\n"})
    assert _classes(red_check(repo, "HEAD~1", "HEAD")) == {"test_adds": "red-error"}


def test_an_overlay_replaces_the_head_test_on_both_sides(fixed_bug):
    weak = "from calc import add\n\ndef test_adds():\n    add(2, 3)\n"
    receipt = red_check(fixed_bug, "HEAD~1", "HEAD", tests=["tests/test_calc.py::test_adds"],
                        overlay={"tests/test_calc.py": weak})
    assert _classes(receipt) == {"test_adds": "green"}


def test_a_shadowed_package_is_drift(tmp_path):
    tree = tmp_path / "tree"
    (tree / "zipimport").mkdir(parents=True)
    (tree / "zipimport" / "__init__.py").write_text("", encoding="utf-8")
    (tree / "calcpkg").mkdir()
    (tree / "calcpkg" / "__init__.py").write_text("", encoding="utf-8")
    prov = provenance(tree)
    assert prov["status"] == "drift"
    assert set(prov["outside"]) == {"zipimport"}


def test_no_changed_tests_means_no_run(tmp_path):
    repo = _repo(tmp_path, {"calc.py": BUGGY}, {"calc.py": FIXED})
    receipt = red_check(repo, "HEAD~1", "HEAD")
    assert receipt["status"] == "no-tests" and receipt["tests"] == []


def test_only_new_and_edited_tests_are_selected():
    before = "def test_a():\n    assert 1\n\ndef test_b():\n    assert 2\n"
    after = before.replace("assert 2", "assert 3") + "\nclass TestC:\n    def test_d(self):\n        pass\n"
    assert changed_tests("tests/t.py", before, after) == ["tests/t.py::test_b",
                                                          "tests/t.py::TestC::test_d"]


@pytest.mark.parametrize("text, names, expected", [
    ("E   ImportError: cannot import name 'mul' from 'calc'\n\ntests/t.py:1: ImportError",
     {"mul"}, "red-missing-symbol"),
    ("E   ImportError: cannot import name 'gone' from 'calc'\n\ntests/t.py:1: ImportError",
     {"mul"}, "red-error"),
    ("E   AttributeError: 'NoneType' object has no attribute 'x'\n\ntests/t.py:3: AttributeError",
     {"x"}, "red-error"),
    ("E   TypeError: f() got an unexpected keyword argument 'strict'\n\ntests/t.py:3: TypeError",
     {"strict"}, "red-missing-symbol"),
    ("E   Failed: DID NOT RAISE <class 'ValueError'>\n\ntests/t.py:6: Failed", set(), "red-assert"),
    ("E   AssertionError\n\nsrc/calc.py:9: AssertionError", set(), "red-error"),
])
def test_failure_causes_are_sorted(text, names, expected):
    assert classify_failure(text, "", names)[0] == expected


def test_a_collection_failure_decides_the_tests_in_that_file():
    xml = ('<testsuites><testsuite><testcase classname="" name="tests.test_x">'
           '<error message="collection failure">E   ImportError: cannot import name '
           "'mul' from 'calc'\n\ntests/test_x.py:1: ImportError</error></testcase>"
           '</testsuite></testsuites>')
    from harness.red_classify import outcome_for
    assert outcome_for("tests/test_x.py::test_mul", parse_junit(xml, {"mul"}))[0] \
        == "red-missing-symbol"
