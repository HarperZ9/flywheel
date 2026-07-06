"""tasks_hard.py — a HARDER held-out set for measuring harness LIFT.

The 8-task easy set saturates single_shot at 100%, so verified-inference has no
headroom to show its lift. These are medium-hard algorithmic tasks in the model's
"frontier zone": solvable, but with edge-case-heavy hidden tests (empty, single,
touching, subtractive, nested, trailing-junk, boundaries) where a greedy first
attempt slips. That is exactly where best-of-N + oracle can rescue a pass single-
shot missed. Same self-validating discipline: every reference solution must pass
its own hidden tests, or the benchmark is broken.
"""
from __future__ import annotations

from .tasks_lib import TaskSpec

HARD_REGISTRY: list[TaskSpec] = [
    TaskSpec(
        "merge_intervals",
        "Implement merge_intervals(intervals): given a list of [start, end] "
        "integer intervals, return the list of merged, non-overlapping intervals "
        "sorted by start. Intervals that only touch (e.g. [1,2] and [2,3]) merge. "
        "Return a list of [start, end] lists. Output ONLY the function definition.",
        "solution.py",
        "def merge_intervals(intervals):\n"
        "    if not intervals:\n        return []\n"
        "    s = sorted(intervals, key=lambda x: x[0])\n"
        "    out = [list(s[0])]\n"
        "    for a, b in s[1:]:\n"
        "        if a <= out[-1][1]:\n            out[-1][1] = max(out[-1][1], b)\n"
        "        else:\n            out.append([a, b])\n"
        "    return out\n",
        "from solution import merge_intervals as f\n"
        "def test_empty():\n    assert f([]) == []\n"
        "def test_single():\n    assert f([[1,4]]) == [[1,4]]\n"
        "def test_overlap():\n    assert f([[1,3],[2,6],[8,10],[15,18]]) == [[1,6],[8,10],[15,18]]\n"
        "def test_touching():\n    assert f([[1,2],[2,3]]) == [[1,3]]\n"
        "def test_unsorted():\n    assert f([[8,10],[1,3],[2,6]]) == [[1,6],[8,10]]\n"
        "def test_nested():\n    assert f([[1,10],[2,3]]) == [[1,10]]\n",
        "hard", max_new_tokens=512),
    TaskSpec(
        "roman_to_int",
        "Implement roman_to_int(s): convert a Roman numeral string to an integer, "
        "handling subtractive notation (IV=4, IX=9, XL=40, XC=90, CD=400, CM=900). "
        "Output ONLY the function definition.",
        "solution.py",
        "def roman_to_int(s):\n"
        "    m = {'I':1,'V':5,'X':10,'L':50,'C':100,'D':500,'M':1000}\n"
        "    total = 0\n"
        "    for i, c in enumerate(s):\n"
        "        if i+1 < len(s) and m[c] < m[s[i+1]]:\n            total -= m[c]\n"
        "        else:\n            total += m[c]\n"
        "    return total\n",
        "from solution import roman_to_int as f\n"
        "def test_simple():\n    assert f('III') == 3\n"
        "def test_sub_iv():\n    assert f('IV') == 4\n"
        "def test_sub_ix():\n    assert f('IX') == 9\n"
        "def test_lviii():\n    assert f('LVIII') == 58\n"
        "def test_big():\n    assert f('MCMXCIV') == 1994\n",
        "hard", max_new_tokens=512),
    TaskSpec(
        "is_balanced",
        "Implement is_balanced(s): return True iff the brackets in s are balanced "
        "and correctly nested, for three bracket types () [] {}. Non-bracket "
        "characters are ignored. Output ONLY the function definition.",
        "solution.py",
        "def is_balanced(s):\n"
        "    pairs = {')':'(', ']':'[', '}':'{'}\n"
        "    st = []\n"
        "    for c in s:\n"
        "        if c in '([{':\n            st.append(c)\n"
        "        elif c in ')]}':\n"
        "            if not st or st.pop() != pairs[c]:\n                return False\n"
        "    return not st\n",
        "from solution import is_balanced as f\n"
        "def test_empty():\n    assert f('') is True\n"
        "def test_ok():\n    assert f('()[]{}') is True\n"
        "def test_nested():\n    assert f('{[()]}') is True\n"
        "def test_mismatch():\n    assert f('(]') is False\n"
        "def test_interleave():\n    assert f('([)]') is False\n"
        "def test_unclosed():\n    assert f('(((') is False\n",
        "hard", max_new_tokens=512),
    TaskSpec(
        "two_sum",
        "Implement two_sum(nums, target): return a list [i, j] with i < j such that "
        "nums[i] + nums[j] == target; return [] if none exists. Assume at most one "
        "answer. Output ONLY the function definition.",
        "solution.py",
        "def two_sum(nums, target):\n"
        "    seen = {}\n"
        "    for i, n in enumerate(nums):\n"
        "        if target - n in seen:\n            return [seen[target - n], i]\n"
        "        seen[n] = i\n"
        "    return []\n",
        "from solution import two_sum as f\n"
        "def test_basic():\n    assert f([2,7,11,15], 9) == [0,1]\n"
        "def test_mid():\n    assert f([3,2,4], 6) == [1,2]\n"
        "def test_dup():\n    assert f([3,3], 6) == [0,1]\n"
        "def test_none():\n    assert f([1,2,3], 100) == []\n"
        "def test_neg():\n    assert f([-3,4,3,90], 0) == [0,2]\n",
        "hard", max_new_tokens=512),
    TaskSpec(
        "run_length_encode",
        "Implement run_length_encode(s): return the run-length encoding where each "
        "run of a character c of length n becomes c followed by n, e.g. 'aaabbc' -> "
        "'a3b2c1'. Empty string returns ''. Output ONLY the function definition.",
        "solution.py",
        "def run_length_encode(s):\n"
        "    if not s:\n        return ''\n"
        "    out = []\n    prev = s[0]; cnt = 1\n"
        "    for c in s[1:]:\n"
        "        if c == prev:\n            cnt += 1\n"
        "        else:\n            out.append(prev + str(cnt)); prev = c; cnt = 1\n"
        "    out.append(prev + str(cnt))\n    return ''.join(out)\n",
        "from solution import run_length_encode as f\n"
        "def test_empty():\n    assert f('') == ''\n"
        "def test_one():\n    assert f('a') == 'a1'\n"
        "def test_runs():\n    assert f('aaabbc') == 'a3b2c1'\n"
        "def test_all_diff():\n    assert f('abc') == 'a1b1c1'\n"
        "def test_all_same():\n    assert f('zzzz') == 'z4'\n",
        "hard", max_new_tokens=512),
    TaskSpec(
        "flatten_nested",
        "Implement flatten_nested(lst): flatten an arbitrarily nested list of "
        "integers into a single flat list, preserving order. Output ONLY the "
        "function definition.",
        "solution.py",
        "def flatten_nested(lst):\n"
        "    out = []\n"
        "    for x in lst:\n"
        "        if isinstance(x, list):\n            out.extend(flatten_nested(x))\n"
        "        else:\n            out.append(x)\n"
        "    return out\n",
        "from solution import flatten_nested as f\n"
        "def test_empty():\n    assert f([]) == []\n"
        "def test_flat():\n    assert f([1,2,3]) == [1,2,3]\n"
        "def test_deep():\n    assert f([1,[2,[3,[4]]]]) == [1,2,3,4]\n"
        "def test_mixed():\n    assert f([[],[1],[2,[3]]]) == [1,2,3]\n",
        "hard", max_new_tokens=512),
    TaskSpec(
        "my_atoi",
        "Implement my_atoi(s): parse a leading integer from s. Skip leading "
        "whitespace, accept an optional single leading + or - sign, then read "
        "consecutive digits, stopping at the first non-digit. Return 0 if no digits. "
        "Output ONLY the function definition.",
        "solution.py",
        "def my_atoi(s):\n"
        "    s = s.lstrip()\n    if not s:\n        return 0\n"
        "    sign = 1; i = 0\n"
        "    if s[0] in '+-':\n        sign = -1 if s[0] == '-' else 1; i = 1\n"
        "    num = 0\n"
        "    while i < len(s) and s[i].isdigit():\n        num = num*10 + int(s[i]); i += 1\n"
        "    return sign * num\n",
        "from solution import my_atoi as f\n"
        "def test_plain():\n    assert f('42') == 42\n"
        "def test_ws_neg():\n    assert f('   -42') == -42\n"
        "def test_trailing():\n    assert f('4193 with words') == 4193\n"
        "def test_words():\n    assert f('words and 987') == 0\n"
        "def test_plus():\n    assert f('+7') == 7\n"
        "def test_empty():\n    assert f('') == 0\n",
        "hard", max_new_tokens=512),
    TaskSpec(
        "spiral_order",
        "Implement spiral_order(matrix): return all elements of a 2D list in "
        "clockwise spiral order starting from the top-left. Handle empty and "
        "non-square matrices. Output ONLY the function definition.",
        "solution.py",
        "def spiral_order(matrix):\n"
        "    if not matrix or not matrix[0]:\n        return []\n"
        "    out = []\n    top, bot = 0, len(matrix)-1\n    left, right = 0, len(matrix[0])-1\n"
        "    while top <= bot and left <= right:\n"
        "        for j in range(left, right+1): out.append(matrix[top][j])\n"
        "        top += 1\n"
        "        for i in range(top, bot+1): out.append(matrix[i][right])\n"
        "        right -= 1\n"
        "        if top <= bot:\n"
        "            for j in range(right, left-1, -1): out.append(matrix[bot][j])\n"
        "            bot -= 1\n"
        "        if left <= right:\n"
        "            for i in range(bot, top-1, -1): out.append(matrix[i][left])\n"
        "            left += 1\n"
        "    return out\n",
        "from solution import spiral_order as f\n"
        "def test_3x3():\n    assert f([[1,2,3],[4,5,6],[7,8,9]]) == [1,2,3,6,9,8,7,4,5]\n"
        "def test_2x2():\n    assert f([[1,2],[3,4]]) == [1,2,4,3]\n"
        "def test_1x1():\n    assert f([[1]]) == [1]\n"
        "def test_empty():\n    assert f([]) == []\n"
        "def test_row():\n    assert f([[1,2,3,4]]) == [1,2,3,4]\n",
        "hard", max_new_tokens=512),
    TaskSpec(
        "longest_common_prefix",
        "Implement longest_common_prefix(strs): return the longest common prefix of "
        "a list of strings, or '' if there is none or the list is empty. Output "
        "ONLY the function definition.",
        "solution.py",
        "def longest_common_prefix(strs):\n"
        "    if not strs:\n        return ''\n"
        "    p = strs[0]\n"
        "    for s in strs[1:]:\n"
        "        while not s.startswith(p):\n            p = p[:-1]\n"
        "            if not p:\n                return ''\n"
        "    return p\n",
        "from solution import longest_common_prefix as f\n"
        "def test_common():\n    assert f(['flower','flow','flight']) == 'fl'\n"
        "def test_none():\n    assert f(['dog','cat']) == ''\n"
        "def test_empty_list():\n    assert f([]) == ''\n"
        "def test_one():\n    assert f(['alone']) == 'alone'\n"
        "def test_empty_str():\n    assert f(['','abc']) == ''\n",
        "hard", max_new_tokens=512),
    TaskSpec(
        "binary_search",
        "Implement binary_search(arr, target): given a sorted ascending list arr, "
        "return the index of target, or -1 if absent. Output ONLY the function "
        "definition.",
        "solution.py",
        "def binary_search(arr, target):\n"
        "    lo, hi = 0, len(arr)-1\n"
        "    while lo <= hi:\n"
        "        mid = (lo+hi)//2\n"
        "        if arr[mid] == target:\n            return mid\n"
        "        elif arr[mid] < target:\n            lo = mid+1\n"
        "        else:\n            hi = mid-1\n"
        "    return -1\n",
        "from solution import binary_search as f\n"
        "def test_found():\n    assert f([1,3,5,7], 5) == 2\n"
        "def test_empty():\n    assert f([], 1) == -1\n"
        "def test_absent():\n    assert f([1,2,3], 4) == -1\n"
        "def test_first():\n    assert f([1,2,3,4,5], 1) == 0\n"
        "def test_last():\n    assert f([1,2,3,4,5], 5) == 4\n"
        "def test_single():\n    assert f([9], 9) == 0\n",
        "hard", max_new_tokens=512),
]
