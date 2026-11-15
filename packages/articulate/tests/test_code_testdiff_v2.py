"""Round-two rules of the test-diff analyzer. Each test pins one rule's behavior
on a small before/after pair and stays paired with the legitimate edit beside it,
so disabling or inverting the rule fails the test."""
import textwrap

from articulate.code import analyze

BASE = textwrap.dedent("""
    import pytest
    from calc import add, ratio

    def test_add():
        assert add(2, 3) == 5
        assert add(-1, 1) == 0

    def test_ratio():
        assert ratio(1, 4) == pytest.approx(0.25, rel=1e-3)
        assert ratio(1, 2) == pytest.approx(0.5, rel=1e-3)

    def test_rejects_zero():
        with pytest.raises(ZeroDivisionError, match="zero"):
            ratio(1, 0)
""")
SRC = {"path": "src/calc.py", "before": "def add(a, b):\n    return a + b\n",
       "after": "def add(a, b):\n    return b + a\n"}


def _rules(before, after, path="tests/test_calc.py", extra=()):
    assert before != after, "the edit under test did not apply"
    report = analyze([{"path": path, "before": before, "after": after}, *extra])
    return sorted((f["rule"], f["tier"]) for f in report["findings"])


def _cut(text, start, end):
    return text.replace(text[text.index(start):text.index(end)], "")


def test_a_test_moved_to_another_file_keeps_its_name_and_is_not_a_deletion():
    after = _cut(BASE, "def test_ratio", "def test_rejects")
    moved = BASE[BASE.index("def test_ratio"):BASE.index("def test_rejects")]
    moved = moved.replace("ratio(", "calc.ratio(").replace("def test_calc.ratio(", "def test_ratio(")
    other = {"path": "tests/test_ratio.py", "before": None,
             "after": "import pytest\nimport calc\n\n" + moved}
    assert "def test_ratio(" in other["after"]
    assert _rules(BASE, after, extra=[other]) == []
    assert _rules(BASE, after) == [("test-deleted", "finding")]


def test_a_test_whose_checks_all_reappear_elsewhere_is_not_a_deletion():
    after = _cut(BASE, "def test_ratio", "def test_rejects")
    moved = BASE[BASE.index("def test_ratio"):BASE.index("def test_rejects")]
    moved = moved.replace("def test_ratio():", "def test_quotients():\n    print('moved')")
    other = {"path": "tests/test_ratio.py", "before": None,
             "after": "import pytest\nfrom calc import ratio\n\n" + moved}
    assert _rules(BASE, after, extra=[other]) == []
    assert _rules(BASE, after) == [("test-deleted", "finding")]


def test_a_parametrize_conversion_keeps_its_count_and_dropping_a_row_does_not():
    rows = '[(2, 3, 5), (-1, 1, 0)]'
    para = BASE.replace(
        "def test_add():\n    assert add(2, 3) == 5\n    assert add(-1, 1) == 0\n",
        f"@pytest.mark.parametrize('a, b, want', {rows})\n"
        "def test_add(a, b, want):\n    assert add(a, b) == want\n")
    assert _rules(BASE, para) == []
    fewer = para.replace(rows, "[(2, 3, 5)]")
    assert _rules(para, fewer) == [("assertion-deleted", "finding")]


def test_a_weakening_in_a_change_that_also_edits_source_is_advisory():
    after = BASE.replace("    assert add(-1, 1) == 0\n", "")
    assert _rules(BASE, after) == [("assertion-deleted", "finding")]
    assert _rules(BASE, after, extra=[SRC]) == [("assertion-deleted", "advisory")]


def test_a_source_edit_does_not_soften_a_skip_or_a_tautology():
    after = BASE.replace("def test_add():", "@pytest.mark.skip\ndef test_add():")
    after += "\ndef test_new():\n    assert True\n"
    assert _rules(BASE, after, extra=[SRC]) == [("assert-true", "finding"),
                                                ("skip-added", "finding")]


def test_a_deleted_test_with_a_new_test_beside_it_is_advisory():
    after = _cut(BASE, "def test_ratio", "def test_rejects")
    assert _rules(BASE, after) == [("test-deleted", "finding")]
    replaced = after + "\ndef test_ratio_of_halves():\n    assert ratio(2, 4) == 0.5\n"
    assert _rules(BASE, replaced) == [("test-deleted", "advisory")]


def test_checks_moved_into_a_new_helper_are_advisory_not_a_finding():
    after = BASE.replace("    assert add(2, 3) == 5\n    assert add(-1, 1) == 0\n",
                         "    assert _sums_ok()\n")
    after += "\ndef _sums_ok():\n    return add(2, 3) == 5 and add(-1, 1) == 0\n"
    assert _rules(BASE, after) == [("assertion-deleted", "advisory")]
    inline = BASE.replace("    assert add(-1, 1) == 0\n", "    assert add(-1, 1) is not None\n")
    assert _rules(BASE, inline) == [("assertion-weakened", "finding")]


def test_a_new_comment_on_a_new_weaker_check_declares_it():
    plain = BASE.replace("    assert add(-1, 1) == 0\n", "    assert add(-1, 1) in (0, -0)\n")
    assert _rules(BASE, plain) == [("assertion-weakened", "finding")]
    noted = BASE.replace("    assert add(-1, 1) == 0\n",
                         "    # signed zero differs by platform here\n"
                         "    assert add(-1, 1) in (0, -0)\n")
    assert _rules(BASE, noted) == [("assertion-weakened", "declared")]


def test_a_check_moved_under_an_if_is_reported_unless_the_guard_names_a_platform():
    guarded = BASE.replace("    assert add(-1, 1) == 0\n",
                           "    if add(2, 3) > 4:\n        assert add(-1, 1) == 0\n")
    assert _rules(BASE, guarded) == [("assertion-made-conditional", "finding")]
    platform = BASE.replace("    assert add(-1, 1) == 0\n",
                            "    if sys.platform != 'win32':\n        assert add(-1, 1) == 0\n")
    assert _rules(BASE, platform) == [("assertion-made-conditional", "declared")]


def test_an_old_tautology_in_an_edited_test_is_not_reported_again():
    old = BASE + "\ndef test_old():\n    total = add(1, 2)\n    assert total == total\n"
    edited = old.replace("    assert total == total\n",
                         "    assert total == total\n    assert add(0, 0) == 0\n")
    assert _rules(old, edited) == []
    fresh = old.replace("    assert total == total\n",
                        "    assert total == total\n    assert 1 == 1\n")
    assert _rules(old, fresh) == [("self-compare", "finding")]


def test_an_empty_list_that_a_fake_fills_is_not_a_constant():
    body = ("    calls = []\n    run(lambda x: calls.append(x))\n    assert calls == []\n")
    after = BASE + "\ndef test_new():\n" + body
    assert _rules(BASE, after) == []
    const = BASE + "\ndef test_new():\n    limit = 3\n    assert limit == 3\n"
    assert _rules(BASE, const) == [("self-compare", "finding")]


def test_an_unchanged_state_check_around_an_act_step_is_not_a_snapshot():
    keep = BASE + ("\ndef test_new():\n    before = snapshot(db)\n    refuse(db)\n"
                   "    assert snapshot(db) == before\n")
    assert _rules(BASE, keep) == []
    snap = BASE + ("\ndef test_new():\n    before = snapshot(db)\n"
                   "    assert snapshot(db) == before\n")
    assert _rules(BASE, snap) == [("snapshot-self", "finding")]


def test_an_except_that_eats_the_assertions_is_reported():
    eaten = BASE.replace(
        "    assert add(2, 3) == 5\n    assert add(-1, 1) == 0\n",
        "    try:\n        assert add(2, 3) == 5\n        assert add(-1, 1) == 0\n"
        "    except Exception as exc:\n        print(exc)\n")
    assert ("exception-swallowed", "finding") in _rules(BASE, eaten)
    reraised = eaten.replace("        print(exc)\n", "        print(exc)\n        raise\n")
    assert _rules(BASE, reraised) == []


def test_a_widened_abs_bound_is_a_widened_tolerance():
    base = BASE + "\ndef test_mean():\n    assert abs(mean([1, 2]) - 1.5) < 0.01\n"
    wide = base.replace("< 0.01", "< 10")
    assert _rules(base, wide) == [("tolerance-widened", "finding")]
    tight = base.replace("< 0.01", "< 0.001")
    assert _rules(base, tight) == []


def test_comparing_a_mock_call_to_its_configured_value_is_reported():
    fake = BASE.replace("    assert add(2, 3) == 5\n",
                        "    fake = Mock(return_value=FIVE)\n    assert fake(row) == FIVE\n")
    assert ("mock-only", "finding") in _rules(BASE, fake)
    real = BASE.replace("    assert add(2, 3) == 5\n",
                        "    fake = Mock(return_value=5)\n    assert apply(fake, 2) == 5\n")
    assert ("mock-only", "finding") not in _rules(BASE, real)


def test_one_comment_above_a_block_of_widened_tolerances_declares_the_block():
    block = BASE.replace("    assert ratio(1, 4)", "    # fma on aarch64 moves the last bits\n"
                         "    assert ratio(1, 4)").replace("rel=1e-3", "rel=1e-2")
    assert _rules(BASE, block) == [("tolerance-widened", "declared")] * 2
    bare = BASE.replace("rel=1e-3", "rel=1e-2")
    assert _rules(BASE, bare) == [("tolerance-widened", "finding")] * 2
