"""Falsifiers for the admission gates — each gate must catch its own failure
mode, and a known-good task must clear all of them.

The load-bearing one is oracle_can_fail: a task whose hidden tests pass a
return-None stub would poison the N>=100 set with free points, and no
downstream eval could see it.
"""
import pytest

from harness.task_curator import (append_registry, curate, load_registry,
                                  screen)
from harness.tasks_lib import TaskSpec

GOOD = TaskSpec(
    "curator_add", "Implement add(a, b) returning the integer sum. Output ONLY "
    "the function definition.", "solution.py",
    "def add(a, b):\n    return a + b\n",
    "from solution import add\n"
    "def test_pos():\n    assert add(2, 3) == 5\n"
    "def test_neg():\n    assert add(-1, -1) == -2\n"
    "def test_zero():\n    assert add(0, 0) == 0\n"
    "def test_big():\n    assert add(10**9, 1) == 10**9 + 1\n",
    "hard")


def _variant(**kw):
    base = dict(task_id="curator_add", prompt=GOOD.prompt,
                candidate_filename="solution.py", solution=GOOD.solution,
                hidden_tests=GOOD.hidden_tests, difficulty="hard")
    base.update(kw)
    return TaskSpec(base.pop("task_id"), base.pop("prompt"),
                    base.pop("candidate_filename"), base.pop("solution"),
                    base.pop("hidden_tests"), base.pop("difficulty"))


def test_good_task_clears_every_gate(tmp_path):
    r = screen(GOOD, tmp_path)
    assert r["gates"] == {k: "PASS" for k in r["gates"]}, r["gates"]
    assert r["admitted"]


def test_vacuous_tests_rejected_by_oracle_can_fail(tmp_path):
    vac = _variant(task_id="vacuous", hidden_tests=(
        "def test_a():\n    assert True\n"
        "def test_b():\n    assert 1 == 1\n"
        "def test_c():\n    assert not False\n"
        "def test_d():\n    assert []==[]\n"))
    r = screen(vac, tmp_path)
    assert not r["admitted"]
    assert r["gates"]["oracle_can_fail"].startswith("FAIL")


def test_broken_reference_rejected(tmp_path):
    bad = _variant(task_id="broken_ref",
                   solution="def add(a, b):\n    return a - b\n")
    r = screen(bad, tmp_path)
    assert not r["admitted"]
    assert r["gates"]["reference_passes"].startswith("FAIL")


def test_solution_leaked_into_prompt_rejected(tmp_path):
    leaky = _variant(task_id="leaky",
                     prompt="Implement add. Hint: def add(a, b): return a + b")
    r = screen(leaky, tmp_path)
    assert r["gates"]["no_solution_leak"].startswith("FAIL")


def test_thin_tests_rejected_by_edge_coverage(tmp_path):
    thin = _variant(task_id="thin", hidden_tests=(
        "from solution import add\n"
        "def test_only():\n    assert add(1, 1) == 2\n"))
    r = screen(thin, tmp_path)
    assert r["gates"]["edge_coverage"].startswith("FAIL")


def test_unstubbable_solution_fails_closed(tmp_path):
    weird = _variant(task_id="unstubbable",
                     solution="add = lambda a, b: a + b\n")
    r = screen(weird, tmp_path)
    assert r["gates"]["oracle_can_fail"].startswith("FAIL")
    assert "fail closed" in r["gates"]["oracle_can_fail"]


def test_batch_dedup_catches_twins_within_one_batch(tmp_path):
    twin = _variant(task_id="curator_add_twin")   # same solution, new id
    out = curate([GOOD, twin], tmp_path)
    assert [s.task_id for s in out["admitted"]] == ["curator_add"]
    assert "dedup" in out["rejected"]["curator_add_twin"]


def test_semantic_dup_in_different_clothes_is_caught(tmp_path):
    # a rewrite of the existing hard task is_balanced: new id, new wording,
    # new function name, different implementation style — same behavior.
    from harness.tasks_hard import HARD_REGISTRY
    disguised = TaskSpec(
        "bracket_check",
        "Write bracket_check(text) that reports whether every parenthesis, "
        "square bracket and curly brace opens and closes properly, ignoring "
        "all other characters in the input text.",
        "solution.py",
        "def bracket_check(text):\n"
        "    need = {'(': ')', '[': ']', '{': '}'}\n"
        "    want = []\n"
        "    for ch in text:\n"
        "        if ch in need:\n            want.append(need[ch])\n"
        "        elif ch in need.values():\n"
        "            if not want or want.pop() != ch:\n                return False\n"
        "    return not want\n",
        "from solution import bracket_check as f\n"
        "def test_a():\n    assert f('([]{})') is True\n"
        "def test_b():\n    assert f('([)]') is False\n"
        "def test_c():\n    assert f('(') is False\n"
        "def test_d():\n    assert f('x(y)z') is True\n",
        "hard")
    r = screen(disguised, tmp_path, existing=list(HARD_REGISTRY))
    assert r["gates"]["dedup"].startswith("FAIL")
    assert "is_balanced" in r["gates"]["dedup"]


def test_complementary_neighbor_survives_semantic_gate(tmp_path):
    # decode vs the existing run_length_encode: textually adjacent (this is
    # the pair text-similarity alone would falsely kill), behaviorally distinct
    from harness.tasks_hard import HARD_REGISTRY
    decode = TaskSpec(
        "rle_decode_probe",
        "Implement rle_decode(s): decode a run-length encoded string of "
        "<count><char> runs back to the original string, e.g. '3a2b' -> "
        "'aaabb'. Counts may span multiple digits.",
        "solution.py",
        "def rle_decode(s):\n"
        "    out, i = [], 0\n"
        "    while i < len(s):\n"
        "        j = i\n"
        "        while j < len(s) and s[j].isdigit():\n            j += 1\n"
        "        out.append(s[j] * int(s[i:j]))\n"
        "        i = j + 1\n"
        "    return ''.join(out)\n",
        "from solution import rle_decode as f\n"
        "def test_a():\n    assert f('3a2b') == 'aaabb'\n"
        "def test_b():\n    assert f('') == ''\n"
        "def test_c():\n    assert f('12a') == 'a'*12\n"
        "def test_d():\n    assert f('1x1y') == 'xy'\n",
        "hard")
    r = screen(decode, tmp_path, existing=list(HARD_REGISTRY))
    assert r["gates"]["dedup"] == "PASS", r["gates"]["dedup"]


def test_generalization_is_subsumption_not_duplicate(tmp_path):
    # rotated-array search passes plain binary_search's tests (it degenerates
    # to it), but binary_search fails the rotated cases — one-way pass must
    # ADMIT. The sweep that motivated this found exactly this pair.
    from harness.tasks_hard import HARD_REGISTRY
    rotated = TaskSpec(
        "rotated_probe",
        "Implement search_rot(nums, target): nums is a sorted list of distinct "
        "integers rotated at an unknown pivot; return the index of target or "
        "-1.",
        "solution.py",
        "def search_rot(nums, target):\n"
        "    lo, hi = 0, len(nums) - 1\n"
        "    while lo <= hi:\n"
        "        mid = (lo + hi) // 2\n"
        "        if nums[mid] == target:\n            return mid\n"
        "        if nums[lo] <= nums[mid]:\n"
        "            if nums[lo] <= target < nums[mid]:\n                hi = mid - 1\n"
        "            else:\n                lo = mid + 1\n"
        "        else:\n"
        "            if nums[mid] < target <= nums[hi]:\n                lo = mid + 1\n"
        "            else:\n                hi = mid - 1\n"
        "    return -1\n",
        "from solution import search_rot as f\n"
        "def test_rot():\n    assert f([4,5,6,7,0,1,2], 0) == 4\n"
        "def test_rot_miss():\n    assert f([4,5,6,7,0,1,2], 3) == -1\n"
        "def test_plain():\n    assert f([1,2,3], 3) == 2\n"
        "def test_empty():\n    assert f([], 1) == -1\n",
        "hard")
    r = screen(rotated, tmp_path, existing=list(HARD_REGISTRY))
    assert r["gates"]["dedup"] == "PASS", r["gates"]["dedup"]


def test_hanging_solution_is_rejected_not_a_crash(tmp_path, monkeypatch):
    # learned from a real batch-3 crash: a TimeoutExpired from one oracle run
    # killed the whole admission batch. A hang must be a gate FAIL.
    import harness.task_curator as tc
    monkeypatch.setattr(tc, "ORACLE_TIMEOUT", 3)
    hang = _variant(task_id="hangs",
                    solution="def add(a, b):\n"
                             "    while True:\n        pass\n")
    r = screen(hang, tmp_path)            # must RETURN, not raise
    assert not r["admitted"]
    assert r["gates"]["reference_passes"].startswith("FAIL")


def test_registry_roundtrip_and_tamper_detection(tmp_path):
    reg = tmp_path / "curated.jsonl"
    append_registry([GOOD], reg)
    (loaded,) = load_registry(reg)
    assert loaded == GOOD
    # tamper one field -> loading must refuse loudly, not eval on it
    text = reg.read_text(encoding="utf-8").replace(
        "return a + b", "return a - b")
    reg.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match="content hash"):
        load_registry(reg)
