#!/usr/bin/env python3
"""seed_hard_v2_b2.py — batch 2 for the N>=100 hard-set lane (target 20/100).

Same contract as batch 1: soundness admission through task_curator gates;
difficulty screening against the served 14B is a later arm. Class-based tasks
are deliberately absent — the falsification stubber handles top-level defs
only, and the curator fails closed on what it cannot stub.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from harness.task_curator import seed_batch
from harness.tasks_lib import TaskSpec

REGISTRY_PATH = Path(__file__).parent.parent / "tasks" / "curated" / "hard_v2.jsonl"

BATCH = [
    TaskSpec(
        "evaluate_rpn",
        "Implement evaluate_rpn(tokens): evaluate a reverse-Polish-notation "
        "expression given as a list of string tokens. Operators are + - * / on "
        "integers; division truncates TOWARD ZERO (so -7/2 is -3). Raise "
        "ValueError on malformed input (too few operands, leftover operands, "
        "unknown token, division by zero). Output ONLY the function definition.",
        "solution.py",
        "def evaluate_rpn(tokens):\n"
        "    st = []\n"
        "    for t in tokens:\n"
        "        if t in ('+', '-', '*', '/'):\n"
        "            if len(st) < 2:\n                raise ValueError('operands')\n"
        "            b, a = st.pop(), st.pop()\n"
        "            if t == '+':\n                st.append(a + b)\n"
        "            elif t == '-':\n                st.append(a - b)\n"
        "            elif t == '*':\n                st.append(a * b)\n"
        "            else:\n"
        "                if b == 0:\n                    raise ValueError('div0')\n"
        "                st.append(int(a / b))\n"
        "        else:\n"
        "            try:\n                st.append(int(t))\n"
        "            except ValueError:\n                raise ValueError(t)\n"
        "    if len(st) != 1:\n        raise ValueError('leftover')\n"
        "    return st[0]\n",
        "import pytest\n"
        "from solution import evaluate_rpn as f\n"
        "def test_simple():\n    assert f(['2','3','+']) == 5\n"
        "def test_trunc_toward_zero():\n    assert f(['-7','2','/']) == -3\n"
        "def test_nested():\n    assert f(['4','13','5','/','+']) == 6\n"
        "def test_too_few():\n"
        "    with pytest.raises(ValueError):\n        f(['+'])\n"
        "def test_leftover():\n"
        "    with pytest.raises(ValueError):\n        f(['1','2'])\n"
        "def test_div0():\n"
        "    with pytest.raises(ValueError):\n        f(['1','0','/'])\n",
        "hard", max_new_tokens=512),
    TaskSpec(
        "lis_length",
        "Implement lis_length(nums): return the length of the longest strictly "
        "increasing subsequence of nums (not necessarily contiguous). Empty list "
        "returns 0. Duplicates do NOT extend a subsequence. Output ONLY the "
        "function definition.",
        "solution.py",
        "def lis_length(nums):\n"
        "    import bisect\n"
        "    tails = []\n"
        "    for x in nums:\n"
        "        i = bisect.bisect_left(tails, x)\n"
        "        if i == len(tails):\n            tails.append(x)\n"
        "        else:\n            tails[i] = x\n"
        "    return len(tails)\n",
        "from solution import lis_length as f\n"
        "def test_empty():\n    assert f([]) == 0\n"
        "def test_classic():\n    assert f([10,9,2,5,3,7,101,18]) == 4\n"
        "def test_all_same():\n    assert f([7,7,7]) == 1\n"
        "def test_decreasing():\n    assert f([5,4,3,2,1]) == 1\n"
        "def test_increasing():\n    assert f([1,2,3,4]) == 4\n"
        "def test_dup_no_extend():\n    assert f([1,2,2,3]) == 3\n",
        "hard", max_new_tokens=512),
    TaskSpec(
        "word_break",
        "Implement word_break(s, words): return True iff s can be segmented "
        "into a sequence of one or more words from the list `words` (words may "
        "be reused). Empty s returns True. Case sensitive. Output ONLY the "
        "function definition.",
        "solution.py",
        "def word_break(s, words):\n"
        "    ws = set(words)\n"
        "    ok = [True] + [False] * len(s)\n"
        "    for i in range(1, len(s) + 1):\n"
        "        for j in range(i):\n"
        "            if ok[j] and s[j:i] in ws:\n"
        "                ok[i] = True\n                break\n"
        "    return ok[len(s)]\n",
        "from solution import word_break as f\n"
        "def test_empty():\n    assert f('', ['a']) is True\n"
        "def test_simple():\n    assert f('leetcode', ['leet','code']) is True\n"
        "def test_reuse():\n    assert f('appleapple', ['apple']) is True\n"
        "def test_no():\n    assert f('catsandog', ['cats','dog','sand','and','cat']) is False\n"
        "def test_case():\n    assert f('Ab', ['ab']) is False\n"
        "def test_overlap_choice():\n    assert f('aaab', ['a','aa','ab']) is True\n",
        "hard", max_new_tokens=512),
    TaskSpec(
        "edit_distance",
        "Implement edit_distance(a, b): return the Levenshtein distance between "
        "strings a and b (minimum single-character insertions, deletions, "
        "substitutions). Either may be empty. Output ONLY the function "
        "definition.",
        "solution.py",
        "def edit_distance(a, b):\n"
        "    prev = list(range(len(b) + 1))\n"
        "    for i, ca in enumerate(a, 1):\n"
        "        cur = [i]\n"
        "        for j, cb in enumerate(b, 1):\n"
        "            cur.append(min(prev[j] + 1, cur[j-1] + 1,\n"
        "                           prev[j-1] + (ca != cb)))\n"
        "        prev = cur\n"
        "    return prev[len(b)]\n",
        "from solution import edit_distance as f\n"
        "def test_both_empty():\n    assert f('', '') == 0\n"
        "def test_one_empty():\n    assert f('abc', '') == 3\n"
        "def test_equal():\n    assert f('same', 'same') == 0\n"
        "def test_classic():\n    assert f('horse', 'ros') == 3\n"
        "def test_sub_only():\n    assert f('kitten', 'sitten') == 1\n"
        "def test_intention():\n    assert f('intention', 'execution') == 5\n",
        "hard", max_new_tokens=512),
    TaskSpec(
        "valid_ipv4",
        "Implement valid_ipv4(s): return True iff s is a strictly valid dotted-"
        "quad IPv4 address: exactly four decimal parts 0-255, no leading zeros "
        "(except '0' itself), no signs, no spaces, no empty parts. Output ONLY "
        "the function definition.",
        "solution.py",
        "def valid_ipv4(s):\n"
        "    parts = s.split('.')\n"
        "    if len(parts) != 4:\n        return False\n"
        "    for p in parts:\n"
        "        if not p.isdigit():\n            return False\n"
        "        if len(p) > 1 and p[0] == '0':\n            return False\n"
        "        if int(p) > 255:\n            return False\n"
        "    return True\n",
        "from solution import valid_ipv4 as f\n"
        "def test_ok():\n    assert f('192.168.0.1') is True\n"
        "def test_zero():\n    assert f('0.0.0.0') is True\n"
        "def test_leading_zero():\n    assert f('192.168.01.1') is False\n"
        "def test_too_big():\n    assert f('256.1.1.1') is False\n"
        "def test_three_parts():\n    assert f('1.2.3') is False\n"
        "def test_sign():\n    assert f('+1.2.3.4') is False\n"
        "def test_empty_part():\n    assert f('1..2.3') is False\n",
        "hard", max_new_tokens=512),
    TaskSpec(
        "first_missing_positive",
        "Implement first_missing_positive(nums): return the smallest positive "
        "integer (>= 1) that does not appear in the list. The list may contain "
        "duplicates, zeros, and negatives; it must NOT be modified. Empty list "
        "returns 1. Output ONLY the function definition.",
        "solution.py",
        "def first_missing_positive(nums):\n"
        "    present = set(nums)\n"
        "    i = 1\n"
        "    while i in present:\n        i += 1\n"
        "    return i\n",
        "from solution import first_missing_positive as f\n"
        "def test_empty():\n    assert f([]) == 1\n"
        "def test_gap():\n    assert f([1,2,0]) == 3\n"
        "def test_classic():\n    assert f([3,4,-1,1]) == 2\n"
        "def test_all_high():\n    assert f([7,8,9]) == 1\n"
        "def test_dups():\n    assert f([1,1,2]) == 3\n"
        "def test_no_mutation():\n    g=[2,1]\n    f(g)\n    assert g == [2,1]\n",
        "hard", max_new_tokens=512),
    TaskSpec(
        "josephus",
        "Implement josephus(n, k): n people stand in a circle numbered 0..n-1. "
        "Counting starts at 0; every k-th person is eliminated (k=1 eliminates "
        "0,1,2,...). Return the number of the survivor. Raise ValueError if "
        "n < 1 or k < 1. Output ONLY the function definition.",
        "solution.py",
        "def josephus(n, k):\n"
        "    if n < 1 or k < 1:\n        raise ValueError((n, k))\n"
        "    pos = 0\n"
        "    for m in range(2, n + 1):\n"
        "        pos = (pos + k) % m\n"
        "    return pos\n",
        "import pytest\n"
        "from solution import josephus as f\n"
        "def test_single():\n    assert f(1, 3) == 0\n"
        "def test_k1():\n    assert f(5, 1) == 4\n"
        "def test_classic():\n    assert f(7, 3) == 3\n"
        "def test_two():\n    assert f(2, 2) == 0\n"
        "def test_bad_n():\n"
        "    with pytest.raises(ValueError):\n        f(0, 1)\n"
        "def test_bad_k():\n"
        "    with pytest.raises(ValueError):\n        f(3, 0)\n",
        "hard", max_new_tokens=512),
    TaskSpec(
        "count_islands",
        "Implement count_islands(grid): given a 2D list of 0/1 integers, return "
        "the number of islands of 1s connected 4-directionally (no diagonals). "
        "Empty grid returns 0. The input grid must NOT be modified. Output ONLY "
        "the function definition.",
        "solution.py",
        "def count_islands(grid):\n"
        "    if not grid or not grid[0]:\n        return 0\n"
        "    rows, cols = len(grid), len(grid[0])\n"
        "    seen = set()\n"
        "    count = 0\n"
        "    for r0 in range(rows):\n"
        "        for c0 in range(cols):\n"
        "            if grid[r0][c0] != 1 or (r0, c0) in seen:\n                continue\n"
        "            count += 1\n"
        "            stack = [(r0, c0)]\n"
        "            seen.add((r0, c0))\n"
        "            while stack:\n"
        "                r, c = stack.pop()\n"
        "                for dr, dc in ((1,0),(-1,0),(0,1),(0,-1)):\n"
        "                    nr, nc = r + dr, c + dc\n"
        "                    if 0 <= nr < rows and 0 <= nc < cols and \\\n"
        "                       grid[nr][nc] == 1 and (nr, nc) not in seen:\n"
        "                        seen.add((nr, nc))\n"
        "                        stack.append((nr, nc))\n"
        "    return count\n",
        "from solution import count_islands as f\n"
        "def test_empty():\n    assert f([]) == 0\n"
        "def test_none():\n    assert f([[0,0],[0,0]]) == 0\n"
        "def test_one_big():\n    assert f([[1,1],[1,1]]) == 1\n"
        "def test_diagonal_not_connected():\n    assert f([[1,0],[0,1]]) == 2\n"
        "def test_classic():\n    assert f([[1,1,0,0],[1,0,0,1],[0,0,1,1]]) == 2\n"
        "def test_no_mutation():\n"
        "    g = [[1,0],[0,1]]\n    f(g)\n    assert g == [[1,0],[0,1]]\n",
        "hard", max_new_tokens=512),
    TaskSpec(
        "next_permutation",
        "Implement next_permutation(nums): rearrange nums IN PLACE into the "
        "lexicographically next greater permutation; if nums is the highest "
        "permutation, wrap to the lowest (sorted ascending). Return the same "
        "list object. Handles duplicates, empty, and single-element lists. "
        "Output ONLY the function definition.",
        "solution.py",
        "def next_permutation(nums):\n"
        "    i = len(nums) - 2\n"
        "    while i >= 0 and nums[i] >= nums[i + 1]:\n        i -= 1\n"
        "    if i >= 0:\n"
        "        j = len(nums) - 1\n"
        "        while nums[j] <= nums[i]:\n            j -= 1\n"
        "        nums[i], nums[j] = nums[j], nums[i]\n"
        "    nums[i + 1:] = reversed(nums[i + 1:])\n"
        "    return nums\n",
        "from solution import next_permutation as f\n"
        "def test_empty():\n    assert f([]) == []\n"
        "def test_simple():\n    assert f([1,2,3]) == [1,3,2]\n"
        "def test_wrap():\n    assert f([3,2,1]) == [1,2,3]\n"
        "def test_dup():\n    assert f([1,1,5]) == [1,5,1]\n"
        "def test_middle():\n    assert f([1,3,2]) == [2,1,3]\n"
        "def test_in_place():\n    m=[1,2]\n    assert f(m) is m and m == [2,1]\n",
        "hard", max_new_tokens=512),
    TaskSpec(
        "merge_sorted_streams",
        "Implement merge_sorted(lists): given a list of already-sorted integer "
        "lists (possibly empty lists, possibly an empty outer list), return one "
        "sorted merged list, stable across duplicates. Do not use sorted() or "
        ".sort() on the combined data — merge. The hidden tests check the "
        "result, not the method, but a correct k-way merge also passes the "
        "large interleaved case. Output ONLY the function definition.",
        "solution.py",
        "def merge_sorted(lists):\n"
        "    import heapq\n"
        "    h = [(lst[0], i, 0) for i, lst in enumerate(lists) if lst]\n"
        "    heapq.heapify(h)\n"
        "    out = []\n"
        "    while h:\n"
        "        val, i, j = heapq.heappop(h)\n"
        "        out.append(val)\n"
        "        if j + 1 < len(lists[i]):\n"
        "            heapq.heappush(h, (lists[i][j + 1], i, j + 1))\n"
        "    return out\n",
        "from solution import merge_sorted as f\n"
        "def test_empty_outer():\n    assert f([]) == []\n"
        "def test_empty_inners():\n    assert f([[], []]) == []\n"
        "def test_two():\n    assert f([[1,4,5],[1,3,4]]) == [1,1,3,4,4,5]\n"
        "def test_singletons():\n    assert f([[2],[1],[3]]) == [1,2,3]\n"
        "def test_one_list():\n    assert f([[1,2,3]]) == [1,2,3]\n"
        "def test_interleaved():\n"
        "    a = list(range(0, 100, 2)); b = list(range(1, 100, 2))\n"
        "    assert f([a, b]) == list(range(100))\n",
        "hard", max_new_tokens=512),
]


def main() -> int:
    out = seed_batch(BATCH, REGISTRY_PATH)
    for tid, bad in out["rejected"].items():
        print(f"REJECTED {tid}: {json.dumps(bad)}")
    print(f"admitted {len(out['admitted'])}/{len(BATCH)} "
          f"(registry total: {out['registry_total']}; lane target: 100)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
