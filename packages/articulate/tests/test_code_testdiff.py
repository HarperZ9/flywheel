"""The test-diff analyzer: each rule fires on its own shape and stays quiet on
the legitimate edit next to it. Every case is a small before/after pair."""
import json
import subprocess
import textwrap

import pytest

from articulate.code import analyze
from articulate.code.cli import main as code_main


def _rules(before, after, path="tests/test_calc.py", extra=(), declared=(), same=False):
    # A replace() that matched nothing would make every case below vacuous.
    assert (before == after) == same, "the edit under test did not apply"
    changes = [{"path": path, "before": before, "after": after}, *extra]
    report = analyze(changes, declared)
    return sorted((f["rule"], f["tier"]) for f in report["findings"]), report


BASE = textwrap.dedent("""
    from calc import add, ratio

    def test_add():
        assert add(2, 3) == 5
        assert add(-1, 1) == 0

    def test_ratio():
        assert ratio(1, 3) == pytest.approx(0.3333, rel=1e-3)

    def test_rejects_zero():
        with pytest.raises(ZeroDivisionError, match="zero"):
            ratio(1, 0)
""")


def test_an_unchanged_file_is_clean():
    rules, report = _rules(BASE, BASE, same=True)
    assert rules == []
    assert report["status"] == "clean"
    assert report["does_not_prove"], "the limits list is never empty"


def test_deleting_an_assertion_is_reported():
    after = BASE.replace("    assert add(-1, 1) == 0\n", "")
    assert _rules(BASE, after)[0] == [("assertion-deleted", "finding")]


def test_weakening_equality_to_not_none_is_reported():
    after = BASE.replace("assert add(2, 3) == 5", "assert add(2, 3) is not None")
    assert _rules(BASE, after)[0] == [("assertion-weakened", "finding")]


def test_changing_the_expected_value_is_not_a_weakening():
    after = BASE.replace("assert add(2, 3) == 5", "assert add(2, 3) == 6")
    assert _rules(BASE, after)[0] == []


def test_widening_a_tolerance_is_reported_unless_a_comment_gives_the_reason():
    wide = BASE.replace("rel=1e-3", "rel=1.0")
    assert _rules(BASE, wide)[0] == [("tolerance-widened", "finding")]
    reasoned = BASE.replace("rel=1e-3)", "rel=1e-2)  # float32 sums drift near 1e-3")
    assert _rules(BASE, reasoned)[0] == [("tolerance-widened", "declared")]


def test_an_added_skip_is_reported_and_a_platform_skipif_is_declared():
    skip = BASE.replace("def test_add():", "@pytest.mark.skip(reason='later')\ndef test_add():")
    assert _rules(BASE, skip)[0] == [("skip-added", "finding")]
    plat = BASE.replace("def test_add():",
                        "@pytest.mark.skipif(sys.platform == 'win32', reason='posix')\n"
                        "def test_add():")
    assert _rules(BASE, plat)[0] == [("skip-added", "declared")]


def test_an_added_xfail_is_reported():
    after = BASE.replace("def test_ratio():", "@pytest.mark.xfail\ndef test_ratio():")
    assert _rules(BASE, after)[0] == [("xfail-added", "finding")]


def test_widening_the_expected_exception_is_reported():
    after = BASE.replace('pytest.raises(ZeroDivisionError, match="zero")',
                         "pytest.raises(Exception)")
    assert _rules(BASE, after)[0] == [("raises-widened", "finding")]


def test_swallowing_the_act_step_is_reported():
    after = BASE.replace("    assert ratio(1, 3)",
                         "    try:\n        ratio(1, 3)\n    except Exception:\n"
                         "        pass\n    assert ratio(1, 3)")
    assert ("exception-swallowed", "finding") in _rules(BASE, after)[0]


def test_renaming_a_test_out_of_collection_is_reported_but_a_plain_rename_is_not():
    hidden = BASE.replace("def test_add():", "def check_add():")
    assert _rules(BASE, hidden)[0] == [("test-uncollected", "finding")]
    renamed = BASE.replace("def test_add():", "def test_add_small_numbers():")
    assert _rules(BASE, renamed)[0] == []


def test_deleting_a_test_is_reported_unless_its_feature_goes_with_it():
    after = BASE.replace(BASE[BASE.index("def test_ratio"):BASE.index("def test_rejects")], "")
    assert _rules(BASE, after)[0] == [("test-deleted", "finding")]
    feature = {"path": "src/calc.py", "before": "def ratio(a, b):\n    return a / b\n",
               "after": "def other():\n    return 1\n"}
    assert _rules(BASE, after, extra=[feature])[0] == [("test-deleted", "declared")]


def test_moving_assertions_into_a_called_helper_is_not_a_deletion():
    after = BASE.replace("    assert add(2, 3) == 5\n    assert add(-1, 1) == 0\n",
                         "    _check_add(add)\n")
    after += "\ndef _check_add(f):\n    assert f(2, 3) == 5\n    assert f(-1, 1) == 0\n"
    assert "_check_add(add)" in after
    assert _rules(BASE, after)[0] == []


def test_splitting_a_test_with_every_assertion_kept_is_not_a_deletion():
    after = BASE.replace("    assert add(-1, 1) == 0\n", "") + (
        "\ndef test_add_inverse():\n    assert add(-1, 1) == 0\n")
    assert after.count("assert add(-1, 1) == 0") == 1
    assert _rules(BASE, after)[0] == []


def test_a_declared_change_is_shown_as_declared():
    after = BASE.replace("    assert add(-1, 1) == 0\n", "")
    declared = [{"test_id": "tests/test_calc.py::test_add", "change": "loosen",
                 "reason": "negative inputs are out of scope now"}]
    assert _rules(BASE, after, declared=declared)[0] == [("assertion-deleted", "declared")]


@pytest.mark.parametrize("body, rule", [
    ("    assert True\n", "assert-true"),
    ("    total = add(1, 2)\n    assert total == total\n", "self-compare"),
    ("    expected = add(1, 2)\n    assert add(1, 2) == expected\n", "snapshot-self"),
    ("    m = Mock()\n    m.return_value = 5\n    assert m() == 5\n", "mock-only"),
    ("    add(1, 2)\n", "no-assertion"),
    ("    m = Mock()\n    run(m)\n    m.assert_called_once()\n", "mock-called-only"),
])
def test_a_new_test_that_cannot_fail_is_reported(body, rule):
    after = BASE + "\ndef test_new():\n" + textwrap.indent(body, "    ")
    rules = _rules(BASE, after)[0]
    assert (rule, "finding") in rules, rules


def test_new_tests_that_check_real_values_are_clean():
    after = BASE + textwrap.dedent("""
        def test_new():
            m = Mock(return_value=5)
            assert run(m) == 10
            m.assert_called_once_with(2)
            first, second = add(1, 2), add(1, 2)
            assert first == second
    """)
    assert _rules(BASE, after)[0] == []


def test_untouched_old_smells_are_not_reported_again():
    smelly = BASE + "\ndef test_old():\n    assert True\n"
    assert _rules(smelly, smelly, same=True)[0] == []


def test_a_whole_file_skip_is_reported():
    after = "import pytest\npytestmark = pytest.mark.skip(reason='flaky')\n" + BASE
    assert _rules(BASE, after)[0] == [("skip-added", "finding")]


def test_unparseable_and_non_python_tests_are_unverifiable_never_clean():
    report = analyze([{"path": "tests/test_x.py", "before": "def test_a(:\n", "after": "x"}])
    assert report["status"] == "unverifiable"
    report = analyze([{"path": "web/tests/app.test.ts", "before": None, "after": None}])
    assert report["status"] == "unverifiable"


def test_the_cli_reads_a_git_range(tmp_path, capsys):
    repo = tmp_path / "repo"
    (repo / "tests").mkdir(parents=True)
    run = lambda *a: subprocess.run(["git", "-C", str(repo), *a], check=True,
                                    capture_output=True)
    run("init", "-q")
    run("config", "user.email", "t@example.invalid")
    run("config", "user.name", "t")
    (repo / "tests" / "test_calc.py").write_text(BASE, encoding="utf-8")
    run("add", ".")
    run("commit", "-q", "-m", "base")
    weak = BASE.replace("assert add(2, 3) == 5", "assert add(2, 3)")
    (repo / "tests" / "test_calc.py").write_text(weak, encoding="utf-8")
    run("commit", "-q", "-am", "head")
    assert code_main(["test-diff", "HEAD~1", "HEAD", "--repo", str(repo), "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert [f["rule"] for f in report["findings"]] == ["assertion-weakened"]
    assert report["mode"] == "report-only"
