"""tasks_expert.py — an EXPERT held-out set to give the uplift measurement headroom.

The hard set left single_shot at 80% on the trained 14B, so the +10% "lift" was one
task inside noise and did not reproduce (the uplift claim is UNEARNED). To ever EARN
it, the eval needs a set where single-shot fails MORE — genuine frontier tasks (DP with
edge cases, subtle two-pointer, in-place permutation) whose reference is correct but
whose greedy first attempt slips on the edge cases the hidden tests target. Same
self-validating discipline: every reference solution must pass its own hidden tests.

This does NOT by itself earn the uplift. It is the prerequisite: run M7 on this set,
report single_shot / verified / N / a CI. If single-shot drops below ~0.6 and verified
beats it outside the interval, the lift is finally measurable. If not, the honest word
stays 'unearned'.
"""
from __future__ import annotations

from .tasks_lib import TaskSpec

EXPERT_REGISTRY: list[TaskSpec] = [
    TaskSpec(
        "edit_distance",
        "Implement edit_distance(a, b): the Levenshtein distance between two strings "
        "(min single-char insert/delete/substitute edits). Output ONLY the function.",
        "solution.py",
        "def edit_distance(a, b):\n"
        "    m, n = len(a), len(b)\n"
        "    dp = list(range(n + 1))\n"
        "    for i in range(1, m + 1):\n"
        "        prev = dp[0]; dp[0] = i\n"
        "        for j in range(1, n + 1):\n"
        "            cur = dp[j]\n"
        "            dp[j] = prev if a[i-1] == b[j-1] else 1 + min(prev, dp[j], dp[j-1])\n"
        "            prev = cur\n"
        "    return dp[n]\n",
        "from solution import edit_distance as f\n"
        "def test_both_empty():\n    assert f('', '') == 0\n"
        "def test_one_empty():\n    assert f('a', '') == 1 and f('', 'abc') == 3\n"
        "def test_equal():\n    assert f('abc', 'abc') == 0\n"
        "def test_horse():\n    assert f('horse', 'ros') == 3\n"
        "def test_intention():\n    assert f('intention', 'execution') == 5\n",
        "expert", max_new_tokens=512),
    TaskSpec(
        "word_break",
        "Implement word_break(s, words): return True iff s can be segmented into a "
        "space-separated sequence of one or more words from the list `words` (words "
        "may be reused). The empty string is breakable. Output ONLY the function.",
        "solution.py",
        "def word_break(s, words):\n"
        "    ws = set(words); n = len(s)\n"
        "    dp = [False] * (n + 1); dp[0] = True\n"
        "    for i in range(1, n + 1):\n"
        "        for j in range(i):\n"
        "            if dp[j] and s[j:i] in ws:\n                dp[i] = True; break\n"
        "    return dp[n]\n",
        "from solution import word_break as f\n"
        "def test_empty():\n    assert f('', ['a']) is True\n"
        "def test_leetcode():\n    assert f('leetcode', ['leet', 'code']) is True\n"
        "def test_reuse():\n    assert f('applepenapple', ['apple', 'pen']) is True\n"
        "def test_fail():\n    assert f('catsandog', ['cats','dog','sand','and','cat']) is False\n"
        "def test_single_fail():\n    assert f('a', ['b']) is False\n",
        "expert", max_new_tokens=512),
    TaskSpec(
        "coin_change",
        "Implement coin_change(coins, amount): the minimum number of coins to make "
        "`amount` from the given coin denominations, or -1 if impossible. amount can "
        "be 0 (answer 0). Output ONLY the function.",
        "solution.py",
        "def coin_change(coins, amount):\n"
        "    INF = amount + 1\n"
        "    dp = [0] + [INF] * amount\n"
        "    for a in range(1, amount + 1):\n"
        "        for c in coins:\n"
        "            if c <= a:\n                dp[a] = min(dp[a], dp[a-c] + 1)\n"
        "    return dp[amount] if dp[amount] <= amount else -1\n",
        "from solution import coin_change as f\n"
        "def test_basic():\n    assert f([1,2,5], 11) == 3\n"
        "def test_impossible():\n    assert f([2], 3) == -1\n"
        "def test_zero():\n    assert f([1], 0) == 0\n"
        "def test_multi():\n    assert f([2,5,10,1], 27) == 4\n"
        "def test_big():\n    assert f([186,419,83,408], 6249) == 20\n",
        "expert", max_new_tokens=512),
    TaskSpec(
        "max_subarray_circular",
        "Implement max_subarray_circular(nums): the maximum sum of a non-empty "
        "subarray of a CIRCULAR integer array (the subarray may wrap around the end). "
        "Handle the all-negative case. Output ONLY the function.",
        "solution.py",
        "def max_subarray_circular(nums):\n"
        "    total = 0\n"
        "    cur_max = 0; best_max = nums[0]\n"
        "    cur_min = 0; best_min = nums[0]\n"
        "    for x in nums:\n"
        "        cur_max = max(cur_max + x, x); best_max = max(best_max, cur_max)\n"
        "        cur_min = min(cur_min + x, x); best_min = min(best_min, cur_min)\n"
        "        total += x\n"
        "    if best_max < 0:\n        return best_max\n"
        "    return max(best_max, total - best_min)\n",
        "from solution import max_subarray_circular as f\n"
        "def test_wrap():\n    assert f([1,-2,3,-2]) == 3\n"
        "def test_wrap2():\n    assert f([5,-3,5]) == 10\n"
        "def test_all_neg():\n    assert f([-3,-2,-3]) == -2\n"
        "def test_mixed():\n    assert f([3,-1,2,-1]) == 4\n"
        "def test_neg2():\n    assert f([-2,-3,-1]) == -1\n",
        "expert", max_new_tokens=512),
    TaskSpec(
        "decode_ways",
        "Implement decode_ways(s): the number of ways to decode a digit string where "
        "'1'..'26' map to 'A'..'Z'. Leading zeros and invalid pairs count as 0 ways. "
        "Output ONLY the function.",
        "solution.py",
        "def decode_ways(s):\n"
        "    if not s or s[0] == '0':\n        return 0\n"
        "    n = len(s)\n"
        "    dp = [0] * (n + 1); dp[0] = 1; dp[1] = 1\n"
        "    for i in range(2, n + 1):\n"
        "        if s[i-1] != '0':\n            dp[i] += dp[i-1]\n"
        "        if 10 <= int(s[i-2:i]) <= 26:\n            dp[i] += dp[i-2]\n"
        "    return dp[n]\n",
        "from solution import decode_ways as f\n"
        "def test_12():\n    assert f('12') == 2\n"
        "def test_226():\n    assert f('226') == 3\n"
        "def test_zero():\n    assert f('0') == 0 and f('06') == 0\n"
        "def test_10():\n    assert f('10') == 1 and f('100') == 0\n"
        "def test_11106():\n    assert f('11106') == 2\n",
        "expert", max_new_tokens=512),
    TaskSpec(
        "trapping_rain_water",
        "Implement trapping_rain_water(heights): given non-negative bar heights, the "
        "units of water trapped after raining. Output ONLY the function.",
        "solution.py",
        "def trapping_rain_water(h):\n"
        "    if not h:\n        return 0\n"
        "    l, r = 0, len(h) - 1\n"
        "    lm, rm = h[l], h[r]; water = 0\n"
        "    while l < r:\n"
        "        if lm < rm:\n            l += 1; lm = max(lm, h[l]); water += lm - h[l]\n"
        "        else:\n            r -= 1; rm = max(rm, h[r]); water += rm - h[r]\n"
        "    return water\n",
        "from solution import trapping_rain_water as f\n"
        "def test_empty():\n    assert f([]) == 0\n"
        "def test_monotone():\n    assert f([1,2,3]) == 0\n"
        "def test_classic():\n    assert f([0,1,0,2,1,0,1,3,2,1,2,1]) == 6\n"
        "def test_valley():\n    assert f([4,2,0,3,2,5]) == 9\n"
        "def test_small():\n    assert f([3,0,2]) == 2\n",
        "expert", max_new_tokens=512),
    TaskSpec(
        "next_permutation",
        "Implement next_permutation(nums): return the next lexicographically greater "
        "permutation of the integer list; if none exists (descending), return the "
        "smallest (ascending). Do not mutate the input. Output ONLY the function.",
        "solution.py",
        "def next_permutation(nums):\n"
        "    nums = list(nums)\n"
        "    i = len(nums) - 2\n"
        "    while i >= 0 and nums[i] >= nums[i+1]:\n        i -= 1\n"
        "    if i >= 0:\n"
        "        j = len(nums) - 1\n"
        "        while nums[j] <= nums[i]:\n            j -= 1\n"
        "        nums[i], nums[j] = nums[j], nums[i]\n"
        "    nums[i+1:] = reversed(nums[i+1:])\n"
        "    return nums\n",
        "from solution import next_permutation as f\n"
        "def test_basic():\n    assert f([1,2,3]) == [1,3,2]\n"
        "def test_wrap():\n    assert f([3,2,1]) == [1,2,3]\n"
        "def test_dup():\n    assert f([1,1,5]) == [1,5,1]\n"
        "def test_single():\n    assert f([1]) == [1]\n"
        "def test_mid():\n    assert f([1,3,2]) == [2,1,3]\n",
        "expert", max_new_tokens=512),
]
