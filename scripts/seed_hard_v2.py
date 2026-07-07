#!/usr/bin/env python3
"""seed_hard_v2.py — first admission batch for the N>=100 hard-set lane.

Every candidate goes through harness.task_curator.screen (reference passes,
oracle can fail, deterministic, no leak, edge coverage, dedup vs the existing
18-task benchmark AND the registry so re-runs are idempotent). Admitted specs
land in tasks/curated/hard_v2.jsonl as hash-carrying rows.

HONEST GAP, by design: these are admitted for SOUNDNESS only. Difficulty
calibration (single-shot 14B must NOT saturate) requires the served model and
happens as a later screening arm — a sound task that turns out easy gets
CULLED then, not granted a place. Do not run the uplift eval on this set
before difficulty screening.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from harness.task_curator import append_registry, curate, load_registry
from harness.tasks_hard import HARD_REGISTRY
from harness.tasks_lib import REGISTRY, TaskSpec

REGISTRY_PATH = Path(__file__).parent.parent / "tasks" / "curated" / "hard_v2.jsonl"

BATCH = [
    TaskSpec(
        "interval_intersection",
        "Implement interval_intersection(a, b): given two lists of [start, end] "
        "closed integer intervals, EACH list already sorted and internally "
        "disjoint, return the sorted list of their intersections as [start, end] "
        "lists. Touching endpoints intersect (e.g. [1,3] and [3,5] -> [3,3]). "
        "Output ONLY the function definition.",
        "solution.py",
        "def interval_intersection(a, b):\n"
        "    out, i, j = [], 0, 0\n"
        "    while i < len(a) and j < len(b):\n"
        "        lo = max(a[i][0], b[j][0])\n"
        "        hi = min(a[i][1], b[j][1])\n"
        "        if lo <= hi:\n            out.append([lo, hi])\n"
        "        if a[i][1] < b[j][1]:\n            i += 1\n"
        "        else:\n            j += 1\n"
        "    return out\n",
        "from solution import interval_intersection as f\n"
        "def test_empty():\n    assert f([], [[1,2]]) == []\n"
        "def test_disjoint():\n    assert f([[1,2]], [[3,4]]) == []\n"
        "def test_touching():\n    assert f([[1,3]], [[3,5]]) == [[3,3]]\n"
        "def test_nested():\n    assert f([[1,10]], [[2,3],[5,6]]) == [[2,3],[5,6]]\n"
        "def test_classic():\n    assert f([[0,2],[5,10],[13,23],[24,25]], [[1,5],[8,12],[15,24],[25,26]]) == [[1,2],[5,5],[8,10],[15,23],[24,24],[25,25]]\n",
        "hard", max_new_tokens=512),
    TaskSpec(
        "balanced_brackets",
        "Implement balanced_brackets(s): return True iff every bracket in s is "
        "balanced and correctly nested. Brackets are ()[]{}. Non-bracket "
        "characters are ignored. An empty string is balanced. Output ONLY the "
        "function definition.",
        "solution.py",
        "def balanced_brackets(s):\n"
        "    pairs = {')': '(', ']': '[', '}': '{'}\n"
        "    stack = []\n"
        "    for c in s:\n"
        "        if c in '([{':\n            stack.append(c)\n"
        "        elif c in pairs:\n"
        "            if not stack or stack.pop() != pairs[c]:\n"
        "                return False\n"
        "    return not stack\n",
        "from solution import balanced_brackets as f\n"
        "def test_empty():\n    assert f('') is True\n"
        "def test_simple():\n    assert f('([]{})') is True\n"
        "def test_crossed():\n    assert f('([)]') is False\n"
        "def test_unclosed():\n    assert f('((') is False\n"
        "def test_extra_close():\n    assert f('())') is False\n"
        "def test_noise():\n    assert f('a(b[c]d)e') is True\n",
        "hard", max_new_tokens=512),
    TaskSpec(
        "spiral_traverse",
        "Implement spiral_traverse(grid): given a rectangular 2D list (rows x "
        "cols, possibly non-square, possibly a single row or column), return the "
        "elements in clockwise spiral order starting at the top-left. Empty grid "
        "returns []. Output ONLY the function definition.",
        "solution.py",
        "def spiral_traverse(grid):\n"
        "    out = []\n"
        "    if not grid or not grid[0]:\n        return out\n"
        "    top, bot = 0, len(grid) - 1\n"
        "    left, right = 0, len(grid[0]) - 1\n"
        "    while top <= bot and left <= right:\n"
        "        for c in range(left, right + 1):\n            out.append(grid[top][c])\n"
        "        for r in range(top + 1, bot + 1):\n            out.append(grid[r][right])\n"
        "        if top < bot and left < right:\n"
        "            for c in range(right - 1, left - 1, -1):\n                out.append(grid[bot][c])\n"
        "            for r in range(bot - 1, top, -1):\n                out.append(grid[r][left])\n"
        "        top += 1; bot -= 1; left += 1; right -= 1\n"
        "    return out\n",
        "from solution import spiral_traverse as f\n"
        "def test_empty():\n    assert f([]) == []\n"
        "def test_square():\n    assert f([[1,2,3],[4,5,6],[7,8,9]]) == [1,2,3,6,9,8,7,4,5]\n"
        "def test_wide():\n    assert f([[1,2,3,4]]) == [1,2,3,4]\n"
        "def test_tall():\n    assert f([[1],[2],[3]]) == [1,2,3]\n"
        "def test_rect():\n    assert f([[1,2,3],[4,5,6]]) == [1,2,3,6,5,4]\n",
        "hard", max_new_tokens=512),
    TaskSpec(
        "search_rotated",
        "Implement search_rotated(nums, target): given a list of DISTINCT "
        "integers that was sorted ascending then rotated at an unknown pivot "
        "(possibly not rotated at all), return the index of target or -1. Must "
        "handle the empty list. O(log n) expected but correctness is what is "
        "tested. Output ONLY the function definition.",
        "solution.py",
        "def search_rotated(nums, target):\n"
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
        "from solution import search_rotated as f\n"
        "def test_empty():\n    assert f([], 1) == -1\n"
        "def test_single_hit():\n    assert f([5], 5) == 0\n"
        "def test_unrotated():\n    assert f([1,2,3,4,5], 4) == 3\n"
        "def test_rotated_hit():\n    assert f([4,5,6,7,0,1,2], 0) == 4\n"
        "def test_rotated_miss():\n    assert f([4,5,6,7,0,1,2], 3) == -1\n"
        "def test_pivot_edge():\n    assert f([3,1], 1) == 1\n",
        "hard", max_new_tokens=512),
    TaskSpec(
        "parse_range_list",
        "Implement parse_range_list(s): parse a string like '1-3,5,7-9' into the "
        "sorted deduplicated list of integers it denotes ([1,2,3,5,7,8,9]). "
        "Ranges are inclusive and may overlap each other or single values. "
        "Whitespace around commas/tokens is allowed. An empty or whitespace-only "
        "string returns []. Raise ValueError on malformed tokens (like '3-1', "
        "'a', '1-'). Output ONLY the function definition.",
        "solution.py",
        "def parse_range_list(s):\n"
        "    vals = set()\n"
        "    s = s.strip()\n"
        "    if not s:\n        return []\n"
        "    for tok in s.split(','):\n"
        "        tok = tok.strip()\n"
        "        if '-' in tok[1:]:\n"
        "            cut = tok.index('-', 1)\n"
        "            a, b = tok[:cut], tok[cut + 1:]\n"
        "            if not a.lstrip('-').isdigit() or not b.lstrip('-').isdigit():\n"
        "                raise ValueError(tok)\n"
        "            lo, hi = int(a), int(b)\n"
        "            if lo > hi:\n                raise ValueError(tok)\n"
        "            vals.update(range(lo, hi + 1))\n"
        "        else:\n"
        "            if not tok.lstrip('-').isdigit():\n"
        "                raise ValueError(tok)\n"
        "            vals.add(int(tok))\n"
        "    return sorted(vals)\n",
        "import pytest\n"
        "from solution import parse_range_list as f\n"
        "def test_empty():\n    assert f('') == []\n"
        "def test_mixed():\n    assert f('1-3,5,7-9') == [1,2,3,5,7,8,9]\n"
        "def test_overlap():\n    assert f('1-4,3-6,4') == [1,2,3,4,5,6]\n"
        "def test_spaces():\n    assert f(' 2 , 4-5 ') == [2,4,5]\n"
        "def test_reversed_range():\n"
        "    with pytest.raises(ValueError):\n        f('3-1')\n"
        "def test_garbage():\n"
        "    with pytest.raises(ValueError):\n        f('1,a')\n"
        "def test_dangling():\n"
        "    with pytest.raises(ValueError):\n        f('1-')\n",
        "hard", max_new_tokens=512),
    TaskSpec(
        "sliding_window_max",
        "Implement sliding_window_max(nums, k): return the list of maxima of "
        "every contiguous window of size k. If k <= 0 raise ValueError; if k > "
        "len(nums) return []. Must handle duplicates and strictly decreasing "
        "input. Output ONLY the function definition.",
        "solution.py",
        "def sliding_window_max(nums, k):\n"
        "    if k <= 0:\n        raise ValueError(k)\n"
        "    if k > len(nums):\n        return []\n"
        "    from collections import deque\n"
        "    dq, out = deque(), []\n"
        "    for i, x in enumerate(nums):\n"
        "        while dq and nums[dq[-1]] <= x:\n            dq.pop()\n"
        "        dq.append(i)\n"
        "        if dq[0] <= i - k:\n            dq.popleft()\n"
        "        if i >= k - 1:\n            out.append(nums[dq[0]])\n"
        "    return out\n",
        "import pytest\n"
        "from solution import sliding_window_max as f\n"
        "def test_classic():\n    assert f([1,3,-1,-3,5,3,6,7], 3) == [3,3,5,5,6,7]\n"
        "def test_k_equals_len():\n    assert f([2,1,4], 3) == [4]\n"
        "def test_k_too_big():\n    assert f([1,2], 5) == []\n"
        "def test_decreasing():\n    assert f([5,4,3,2,1], 2) == [5,4,3,2]\n"
        "def test_duplicates():\n    assert f([2,2,2], 2) == [2,2]\n"
        "def test_bad_k():\n"
        "    with pytest.raises(ValueError):\n        f([1], 0)\n",
        "hard", max_new_tokens=512),
    TaskSpec(
        "topo_sort",
        "Implement topo_sort(n, edges): given n nodes labeled 0..n-1 and a list "
        "of directed edges [u, v] meaning u must come before v, return ANY valid "
        "topological order as a list, or None if the graph has a cycle. "
        "Isolated nodes must appear. n=0 returns []. Output ONLY the function "
        "definition.",
        "solution.py",
        "def topo_sort(n, edges):\n"
        "    adj = [[] for _ in range(n)]\n"
        "    indeg = [0] * n\n"
        "    for u, v in edges:\n"
        "        adj[u].append(v)\n        indeg[v] += 1\n"
        "    stack = [i for i in range(n) if indeg[i] == 0]\n"
        "    out = []\n"
        "    while stack:\n"
        "        u = stack.pop()\n"
        "        out.append(u)\n"
        "        for v in adj[u]:\n"
        "            indeg[v] -= 1\n"
        "            if indeg[v] == 0:\n                stack.append(v)\n"
        "    return out if len(out) == n else None\n",
        "from solution import topo_sort as f\n"
        "def _ok(n, edges, order):\n"
        "    if order is None or sorted(order) != list(range(n)):\n        return False\n"
        "    pos = {x: i for i, x in enumerate(order)}\n"
        "    return all(pos[u] < pos[v] for u, v in edges)\n"
        "def test_empty():\n    assert f(0, []) == []\n"
        "def test_chain():\n    assert _ok(3, [[0,1],[1,2]], f(3, [[0,1],[1,2]]))\n"
        "def test_diamond():\n    e=[[0,1],[0,2],[1,3],[2,3]]\n    assert _ok(4, e, f(4, e))\n"
        "def test_cycle():\n    assert f(2, [[0,1],[1,0]]) is None\n"
        "def test_self_loop():\n    assert f(1, [[0,0]]) is None\n"
        "def test_isolated():\n    assert _ok(4, [[1,2]], f(4, [[1,2]]))\n",
        "hard", max_new_tokens=512),
    TaskSpec(
        "longest_common_prefix_list",
        "Implement longest_common_prefix(strs): return the longest string that "
        "is a prefix of EVERY string in the list. Empty list returns ''. A list "
        "containing an empty string returns ''. Case sensitive. Output ONLY the "
        "function definition.",
        "solution.py",
        "def longest_common_prefix(strs):\n"
        "    if not strs:\n        return ''\n"
        "    lo, hi = min(strs), max(strs)\n"
        "    i = 0\n"
        "    while i < len(lo) and lo[i] == hi[i]:\n        i += 1\n"
        "    return lo[:i]\n",
        "from solution import longest_common_prefix as f\n"
        "def test_empty_list():\n    assert f([]) == ''\n"
        "def test_common():\n    assert f(['flower','flow','flight']) == 'fl'\n"
        "def test_none_common():\n    assert f(['dog','racecar','car']) == ''\n"
        "def test_contains_empty():\n    assert f(['abc','']) == ''\n"
        "def test_identical():\n    assert f(['same','same']) == 'same'\n"
        "def test_case():\n    assert f(['Abc','abc']) == ''\n",
        "hard", max_new_tokens=512),
    TaskSpec(
        "rle_decode",
        "Implement rle_decode(s): decode a run-length-encoded string where each "
        "run is <count><char> with count a positive integer that may span "
        "multiple digits (e.g. '12a2b' -> 'a'*12 + 'bb'). The empty string "
        "decodes to ''. Raise ValueError if the string is malformed (a run "
        "without a count, a count without a char, count of 0). Output ONLY the "
        "function definition.",
        "solution.py",
        "def rle_decode(s):\n"
        "    out, i = [], 0\n"
        "    while i < len(s):\n"
        "        j = i\n"
        "        while j < len(s) and s[j].isdigit():\n            j += 1\n"
        "        if j == i or j == len(s):\n            raise ValueError(s[i:])\n"
        "        n = int(s[i:j])\n"
        "        if n == 0:\n            raise ValueError(s[i:j])\n"
        "        out.append(s[j] * n)\n"
        "        i = j + 1\n"
        "    return ''.join(out)\n",
        "import pytest\n"
        "from solution import rle_decode as f\n"
        "def test_empty():\n    assert f('') == ''\n"
        "def test_simple():\n    assert f('3a1b') == 'aaab'\n"
        "def test_multidigit():\n    assert f('12a2b') == 'a'*12 + 'bb'\n"
        "def test_no_count():\n"
        "    with pytest.raises(ValueError):\n        f('ab')\n"
        "def test_trailing_count():\n"
        "    with pytest.raises(ValueError):\n        f('3a2')\n"
        "def test_zero_count():\n"
        "    with pytest.raises(ValueError):\n        f('0a')\n",
        "hard", max_new_tokens=512),
    TaskSpec(
        "matrix_rotate_inplace",
        "Implement rotate(matrix): rotate an n x n 2D list 90 degrees clockwise "
        "IN PLACE and return the same list object. n may be 0 or 1. Output ONLY "
        "the function definition.",
        "solution.py",
        "def rotate(matrix):\n"
        "    n = len(matrix)\n"
        "    for i in range(n):\n"
        "        for j in range(i + 1, n):\n"
        "            matrix[i][j], matrix[j][i] = matrix[j][i], matrix[i][j]\n"
        "    for row in matrix:\n        row.reverse()\n"
        "    return matrix\n",
        "from solution import rotate as f\n"
        "def test_empty():\n    assert f([]) == []\n"
        "def test_one():\n    assert f([[7]]) == [[7]]\n"
        "def test_two():\n    assert f([[1,2],[3,4]]) == [[3,1],[4,2]]\n"
        "def test_three():\n    assert f([[1,2,3],[4,5,6],[7,8,9]]) == [[7,4,1],[8,5,2],[9,6,3]]\n"
        "def test_in_place():\n    m=[[1,2],[3,4]]\n    assert f(m) is m\n",
        "hard", max_new_tokens=512),
]


def main() -> int:
    existing = list(REGISTRY) + list(HARD_REGISTRY)
    if REGISTRY_PATH.exists():
        existing += load_registry(REGISTRY_PATH)   # idempotent re-runs
    with tempfile.TemporaryDirectory() as wr:
        out = curate(BATCH, wr, existing=existing)
    for tid, bad in out["rejected"].items():
        print(f"REJECTED {tid}:")
        for gate, why in bad.items():
            print(f"  {gate}: {why}")
    n = append_registry(out["admitted"], REGISTRY_PATH)
    total = len(load_registry(REGISTRY_PATH))
    print(f"admitted {n}/{len(BATCH)} -> {REGISTRY_PATH.name} "
          f"(registry total: {total}; lane target: 100)")
    return 0 if not out["rejected"] else 1


if __name__ == "__main__":
    sys.exit(main())
