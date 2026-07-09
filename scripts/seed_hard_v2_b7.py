#!/usr/bin/env python3
"""seed_hard_v2_b7.py - batch 7 for the N>=100 hard-set lane (target ~80/100).

Same contract as batches 1-6: soundness admission through task_curator gates;
difficulty screening against the served 14B is a later arm. Batch 7 doctrine:
contract density over textbook fame. Difficulty comes from precise multi-clause
prose contracts (canonical ordering, tie-breaking, exact exception types,
windowing semantics, small parsers and evaluators) not famous algorithms.
Domains in this file are ones the first 50 barely touch: frequency ranking with
tie-breaks, run-length grouping, boolean-expression evaluation, glob matching,
sliding windows, integer-range summarization, matrix transpose, JSON string
escaping, path normalization, dotted-quad packing, multiset difference, A1
reference parsing, linked-list cycle detection, Manhattan tour length, key-value
parsing, list rotation, anagram grouping, and monotonic-stack stock spans. Each
task is a single top-level function; the prompt states the full contract in prose
with no solution code; the hidden tests assert exact semantics on adversarial
edges.
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
        "top_k_frequent",
        "Write a Python function top_k(items, k) that returns the k most frequent "
        "strings in a list, as a list of the strings themselves (not their "
        "counts). k must be an int, must not be a bool, and must be at least 0; "
        "otherwise -> ValueError('bad k'). Every element of items must be a str; "
        "any non-string element -> ValueError('bad item'). Rank the distinct "
        "strings by descending frequency, breaking ties by ascending "
        "lexicographic (ASCII) order of the string, and return the first k of that "
        "ranking. When k is 0 return the empty list. When k exceeds the number of "
        "distinct strings, return all distinct strings in ranked order (never pad "
        "and never repeat). Output ONLY the function definition.",
        "solution.py",
        r'''def top_k(items, k):
    if not isinstance(k, int) or isinstance(k, bool) or k < 0:
        raise ValueError("bad k")
    counts = {}
    for it in items:
        if not isinstance(it, str):
            raise ValueError("bad item")
        counts[it] = counts.get(it, 0) + 1
    ordered = sorted(counts, key=lambda w: (-counts[w], w))
    return ordered[:k]
''',
        r'''import pytest
from solution import top_k as f
def test_basic(): assert f(['a', 'b', 'a', 'c', 'b', 'a'], 2) == ['a', 'b']
def test_all_tie(): assert f(['a', 'b', 'c'], 2) == ['a', 'b']
def test_k_exceeds(): assert f(['b', 'a'], 5) == ['a', 'b']
def test_empty(): assert f([], 3) == []
def test_k_zero(): assert f(['x', 'x'], 0) == []
def test_tie_break(): assert f(['z', 'a', 'z', 'a'], 1) == ['a']
def test_bad_k():
    with pytest.raises(ValueError) as e: f([], -1)
    assert str(e.value) == 'bad k'
def test_bad_item():
    with pytest.raises(ValueError) as e: f([1, 2], 1)
    assert str(e.value) == 'bad item'
def test_bool_k():
    with pytest.raises(ValueError): f([], True)
''',
        "hard", max_new_tokens=768),
    TaskSpec(
        "uniq_counts",
        "Write a Python function uniq_counts(items) that collapses each maximal "
        "run of equal consecutive elements into a two-element list [value, "
        "run_length] and returns the list of those pairs, in order. items must be "
        "a list; otherwise -> ValueError('bad input'). Only ADJACENT equal "
        "elements merge, so a value that reappears after a different value starts "
        "a fresh run. Two elements merge only when they are equal AND of the same "
        "type, so an integer 1 and the boolean True never merge into one run even "
        "though they compare equal. The empty list returns the empty list. Output "
        "ONLY the function definition.",
        "solution.py",
        r'''def uniq_counts(items):
    if not isinstance(items, list):
        raise ValueError("bad input")
    out = []
    for x in items:
        if out and type(out[-1][0]) is type(x) and out[-1][0] == x:
            out[-1][1] += 1
        else:
            out.append([x, 1])
    return out
''',
        r'''import pytest
from solution import uniq_counts as f
def test_basic(): assert f([1, 1, 2, 3, 3, 3]) == [[1, 2], [2, 1], [3, 3]]
def test_empty(): assert f([]) == []
def test_strings(): assert f(['a', 'a', 'b']) == [['a', 2], ['b', 1]]
def test_single(): assert f([5]) == [[5, 1]]
def test_reappear(): assert f([1, 2, 1]) == [[1, 1], [2, 1], [1, 1]]
def test_type_guard(): assert f([1, True]) == [[1, 1], [True, 1]]
def test_bad_input():
    with pytest.raises(ValueError) as e: f('aa')
    assert str(e.value) == 'bad input'
''',
        "hard", max_new_tokens=768),
    TaskSpec(
        "eval_bool_expr",
        "Write a Python function eval_bool(expr) that evaluates a boolean "
        "expression string and returns a bool. expr must be a str; otherwise -> "
        "ValueError('bad expr'). After removing all whitespace the expression is "
        "built from these single characters only: T for true, F for false, the "
        "operators for logical and, or, and not, and round parentheses for "
        "grouping. The and operator binds tighter than the or operator, and the "
        "not operator binds tightest of all and may stack. Evaluation is "
        "left to right within a precedence level. Any character outside the "
        "allowed set, any unbalanced parenthesis, any missing operand, and any "
        "leftover unparsed input each -> ValueError('bad expr'); in particular the "
        "empty string is invalid. Use the ampersand for and, the vertical bar for "
        "or, and the exclamation mark for not. Output ONLY the function "
        "definition.",
        "solution.py",
        r'''def eval_bool(expr):
    if not isinstance(expr, str):
        raise ValueError("bad expr")
    toks = [c for c in expr if not c.isspace()]
    for c in toks:
        if c not in "TF&|!()":
            raise ValueError("bad expr")
    pos = 0

    def peek():
        return toks[pos] if pos < len(toks) else None

    def eat(ch):
        nonlocal pos
        if peek() != ch:
            raise ValueError("bad expr")
        pos += 1

    def factor():
        c = peek()
        if c == "!":
            eat("!")
            return not factor()
        if c == "(":
            eat("(")
            v = disjunction()
            eat(")")
            return v
        if c == "T":
            eat("T")
            return True
        if c == "F":
            eat("F")
            return False
        raise ValueError("bad expr")

    def conjunction():
        v = factor()
        while peek() == "&":
            eat("&")
            rhs = factor()
            v = v and rhs
        return v

    def disjunction():
        v = conjunction()
        while peek() == "|":
            eat("|")
            rhs = conjunction()
            v = v or rhs
        return v

    result = disjunction()
    if pos != len(toks):
        raise ValueError("bad expr")
    return result
''',
        r'''import pytest
from solution import eval_bool as f
def test_true(): assert f('T') is True
def test_false(): assert f('F') is False
def test_and(): assert f('T&F') is False
def test_or(): assert f('T|F') is True
def test_not(): assert f('!T') is False
def test_not_precedence(): assert f('!F&T') is True
def test_and_before_or(): assert f('T|F&F') is True
def test_parens(): assert f('(T|F)&F') is False
def test_not_group(): assert f('!(T&F)') is True
def test_bad_char():
    with pytest.raises(ValueError) as e: f('T+F')
    assert str(e.value) == 'bad expr'
def test_unbalanced():
    with pytest.raises(ValueError): f('(T')
def test_trailing():
    with pytest.raises(ValueError): f('TT')
def test_empty():
    with pytest.raises(ValueError): f('')
''',
        "hard", max_new_tokens=768),
    TaskSpec(
        "glob_match",
        "Write a Python function glob_match(pattern, name) that reports whether a "
        "name matches a glob pattern and returns a bool. Both arguments must be "
        "strings; otherwise -> ValueError('bad input'). The pattern uses two "
        "wildcards: a star matches any run of zero or more characters, and a "
        "question mark matches exactly one character. Every other character is a "
        "literal that must match itself. The match is anchored: the pattern must "
        "match the ENTIRE name, not a prefix or a substring. There are no "
        "character classes or escaping. So a star followed by .txt matches any "
        "name ending in .txt including one where the star matches nothing, a "
        "question mark matches a single character but not zero characters, and an "
        "empty pattern matches only the empty name. Output ONLY the function "
        "definition.",
        "solution.py",
        r'''def glob_match(pattern, name):
    if not isinstance(pattern, str) or not isinstance(name, str):
        raise ValueError("bad input")
    memo = {}

    def m(pi, ni):
        if (pi, ni) in memo:
            return memo[(pi, ni)]
        if pi == len(pattern):
            res = ni == len(name)
        else:
            c = pattern[pi]
            if c == "*":
                res = m(pi + 1, ni) or (ni < len(name) and m(pi, ni + 1))
            elif c == "?":
                res = ni < len(name) and m(pi + 1, ni + 1)
            else:
                res = ni < len(name) and name[ni] == c and m(pi + 1, ni + 1)
        memo[(pi, ni)] = res
        return res

    return m(0, 0)
''',
        r'''import pytest
from solution import glob_match as f
def test_star_ext(): assert f('*.txt', 'file.txt') is True
def test_star_ext_no(): assert f('*.txt', 'file.py') is False
def test_question(): assert f('?at', 'cat') is True
def test_question_zero(): assert f('?at', 'at') is False
def test_star_empty(): assert f('*', '') is True
def test_star_between(): assert f('a*b', 'ab') is True
def test_star_middle(): assert f('a*b', 'aXXb') is True
def test_star_no_tail(): assert f('a*b', 'aXX') is False
def test_empty_both(): assert f('', '') is True
def test_empty_pattern(): assert f('', 'x') is False
def test_bad_input():
    with pytest.raises(ValueError) as e: f(1, 'a')
    assert str(e.value) == 'bad input'
''',
        "hard", max_new_tokens=768),
    TaskSpec(
        "sliding_windows",
        "Write a Python function sliding_windows(items, size, step) that returns "
        "the list of fixed-size sliding windows over a list. items must be a list; "
        "otherwise -> ValueError('bad input'). size must be an int, not a bool, at "
        "least 1; otherwise -> ValueError('bad size'). step must be an int, not a "
        "bool, at least 1; otherwise -> ValueError('bad step'). A window is a "
        "sublist of exactly `size` consecutive elements; windows start at index 0, "
        "then step, then two times step, and so on. Only FULL windows are "
        "produced: any trailing partial window that would run past the end of the "
        "list is dropped. If the list is shorter than one full window the result "
        "is the empty list. Each window is a new list. Output ONLY the function "
        "definition.",
        "solution.py",
        r'''def sliding_windows(items, size, step):
    if not isinstance(items, list):
        raise ValueError("bad input")
    for value, name in ((size, "size"), (step, "step")):
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ValueError("bad " + name)
    out = []
    i = 0
    while i + size <= len(items):
        out.append(items[i:i + size])
        i += step
    return out
''',
        r'''import pytest
from solution import sliding_windows as f
def test_step_one(): assert f([1, 2, 3, 4], 2, 1) == [[1, 2], [2, 3], [3, 4]]
def test_step_two(): assert f([1, 2, 3, 4, 5], 2, 2) == [[1, 2], [3, 4]]
def test_full(): assert f([1, 2, 3], 3, 1) == [[1, 2, 3]]
def test_too_big(): assert f([1, 2], 3, 1) == []
def test_overlap(): assert f([1, 2, 3, 4, 5], 3, 2) == [[1, 2, 3], [3, 4, 5]]
def test_empty(): assert f([], 1, 1) == []
def test_bad_size():
    with pytest.raises(ValueError) as e: f([1], 0, 1)
    assert str(e.value) == 'bad size'
def test_bad_step():
    with pytest.raises(ValueError) as e: f([1], 1, 0)
    assert str(e.value) == 'bad step'
def test_bad_input():
    with pytest.raises(ValueError) as e: f('ab', 1, 1)
    assert str(e.value) == 'bad input'
''',
        "hard", max_new_tokens=768),
    TaskSpec(
        "summarize_ranges",
        "Write a Python function summarize_ranges(nums) that summarizes a strictly "
        "increasing list of integers into a list of range strings. Every element "
        "must be an int and not a bool; any other element -> ValueError('bad "
        "item'). The list must be strictly increasing, so each element is greater "
        "than the one before; an element that is equal to or less than its "
        "predecessor -> ValueError('not sorted'). Walk the list and coalesce each "
        "maximal run of consecutive integers (each exactly one more than the last) "
        "into a single entry. A run of length one becomes the decimal string of "
        "that number; a longer run becomes the first number, then the two "
        "characters made of a hyphen and a greater-than sign, then the last "
        "number. The empty list returns the empty list. Output ONLY the function "
        "definition.",
        "solution.py",
        r'''def summarize_ranges(nums):
    prev = None
    for x in nums:
        if not isinstance(x, int) or isinstance(x, bool):
            raise ValueError("bad item")
        if prev is not None and x <= prev:
            raise ValueError("not sorted")
        prev = x
    out = []
    i, n = 0, len(nums)
    while i < n:
        j = i
        while j + 1 < n and nums[j + 1] == nums[j] + 1:
            j += 1
        if j == i:
            out.append(str(nums[i]))
        else:
            out.append(str(nums[i]) + "->" + str(nums[j]))
        i = j + 1
    return out
''',
        r'''import pytest
from solution import summarize_ranges as f
def test_basic(): assert f([0, 1, 2, 4, 5, 7]) == ['0->2', '4->5', '7']
def test_empty(): assert f([]) == []
def test_single(): assert f([1]) == ['1']
def test_all_isolated(): assert f([1, 3, 5]) == ['1', '3', '5']
def test_negatives(): assert f([-3, -2, -1, 2]) == ['-3->-1', '2']
def test_one_run(): assert f([1, 2, 3, 4]) == ['1->4']
def test_not_sorted():
    with pytest.raises(ValueError) as e: f([3, 1])
    assert str(e.value) == 'not sorted'
def test_duplicate():
    with pytest.raises(ValueError) as e: f([1, 1])
    assert str(e.value) == 'not sorted'
def test_bad_item():
    with pytest.raises(ValueError) as e: f([1, True])
    assert str(e.value) == 'bad item'
''',
        "hard", max_new_tokens=768),
    TaskSpec(
        "matrix_transpose",
        "Write a Python function transpose(m) that returns the transpose of a "
        "rectangular matrix. m must be a list; otherwise -> ValueError('bad "
        "matrix'). Each element of m is a row and must itself be a list; any row "
        "that is not a list -> ValueError('bad matrix'). All rows must have the "
        "same length; a row whose length differs from the first row's length -> "
        "ValueError('ragged'). The transpose swaps rows and columns, so the cell "
        "at row r and column c of the input becomes the cell at row c and column r "
        "of the output. A matrix with no rows, and a matrix whose rows are all "
        "empty, each transpose to the empty list. Cell values are copied as-is. "
        "Output ONLY the function definition.",
        "solution.py",
        r'''def transpose(m):
    if not isinstance(m, list):
        raise ValueError("bad matrix")
    width = None
    for row in m:
        if not isinstance(row, list):
            raise ValueError("bad matrix")
        if width is None:
            width = len(row)
        elif len(row) != width:
            raise ValueError("ragged")
    if not m or width == 0:
        return []
    return [[m[r][c] for r in range(len(m))] for c in range(width)]
''',
        r'''import pytest
from solution import transpose as f
def test_basic(): assert f([[1, 2, 3], [4, 5, 6]]) == [[1, 4], [2, 5], [3, 6]]
def test_column(): assert f([[1], [2], [3]]) == [[1, 2, 3]]
def test_square(): assert f([[1, 2], [3, 4]]) == [[1, 3], [2, 4]]
def test_no_rows(): assert f([]) == []
def test_empty_rows(): assert f([[]]) == []
def test_single(): assert f([[7]]) == [[7]]
def test_ragged():
    with pytest.raises(ValueError) as e: f([[1, 2], [3]])
    assert str(e.value) == 'ragged'
def test_bad_row():
    with pytest.raises(ValueError) as e: f([1, 2])
    assert str(e.value) == 'bad matrix'
def test_bad_matrix():
    with pytest.raises(ValueError): f('x')
''',
        "hard", max_new_tokens=768),
    TaskSpec(
        "json_string_escape",
        "Write a Python function json_escape(s) that returns the JSON-escaped form "
        "of a string WITHOUT surrounding quotes. s must be a str; otherwise -> "
        "ValueError('bad input'). Apply exactly these replacements. A double quote "
        "becomes a backslash followed by a double quote. A backslash becomes two "
        "backslashes. A newline becomes a backslash followed by the letter n. A "
        "carriage return becomes a backslash followed by the letter r. A tab "
        "becomes a backslash followed by the letter t. A backspace (code point 8) "
        "becomes a backslash followed by the letter b. A form feed (code point 12) "
        "becomes a backslash followed by the letter f. Any other control "
        "character whose code point is below 32 becomes a six-character sequence: "
        "a backslash, the letter u, then exactly four lowercase hexadecimal digits "
        "of the code point. Every other character passes through unchanged. Output "
        "ONLY the function definition.",
        "solution.py",
        r'''def json_escape(s):
    if not isinstance(s, str):
        raise ValueError("bad input")
    special = {'"': '\\"', "\\": "\\\\", "\n": "\\n", "\r": "\\r",
               "\t": "\\t", "\b": "\\b", "\f": "\\f"}
    out = []
    for ch in s:
        if ch in special:
            out.append(special[ch])
        elif ord(ch) < 0x20:
            out.append("\\u%04x" % ord(ch))
        else:
            out.append(ch)
    return "".join(out)
''',
        r'''import pytest
from solution import json_escape as f
def test_quote(): assert f('a"b') == 'a\\"b'
def test_backslash(): assert f('a\\b') == 'a\\\\b'
def test_newline(): assert f('x\ny') == 'x\\ny'
def test_tab(): assert f('\t') == '\\t'
def test_backspace(): assert f(chr(8)) == '\\b'
def test_formfeed(): assert f(chr(12)) == '\\f'
def test_ctrl_zero(): assert f(chr(0)) == '\\u0000'
def test_ctrl_31(): assert f(chr(31)) == '\\u001f'
def test_plain(): assert f('hello') == 'hello'
def test_bad_input():
    with pytest.raises(ValueError) as e: f(5)
    assert str(e.value) == 'bad input'
''',
        "hard", max_new_tokens=768),
    TaskSpec(
        "normalize_path",
        "Write a Python function normalize_path(p) that normalizes an absolute "
        "Unix-style path and returns the canonical string. p must be a str; "
        "otherwise -> ValueError('bad path'). The path must be absolute, meaning "
        "it starts with a forward slash; otherwise -> ValueError('not absolute'). "
        "Split on slashes and process segments left to right: an empty segment "
        "(from a repeated slash) and a single-dot segment are both discarded; a "
        "double-dot segment removes the most recent surviving segment, but at the "
        "root it has no effect and cannot rise above the root; any other segment "
        "is kept literally. Rebuild the path with single slashes and a single "
        "leading slash. Any trailing slash is dropped, except that the root itself "
        "normalizes to a lone slash. Output ONLY the function definition.",
        "solution.py",
        r'''def normalize_path(p):
    if not isinstance(p, str):
        raise ValueError("bad path")
    if not p.startswith("/"):
        raise ValueError("not absolute")
    parts = []
    for seg in p.split("/"):
        if seg == "" or seg == ".":
            continue
        if seg == "..":
            if parts:
                parts.pop()
        else:
            parts.append(seg)
    return "/" + "/".join(parts)
''',
        r'''import pytest
from solution import normalize_path as f
def test_plain(): assert f('/a/b/c') == '/a/b/c'
def test_double_slash(): assert f('/a//b') == '/a/b'
def test_dot(): assert f('/a/./b') == '/a/b'
def test_dotdot(): assert f('/a/b/../c') == '/a/c'
def test_root(): assert f('/') == '/'
def test_above_root(): assert f('/..') == '/'
def test_collapse_all(): assert f('/a/../..') == '/'
def test_trailing(): assert f('/a/b/') == '/a/b'
def test_dotdot_from_root(): assert f('/../a') == '/a'
def test_not_absolute():
    with pytest.raises(ValueError) as e: f('a/b')
    assert str(e.value) == 'not absolute'
def test_bad_path():
    with pytest.raises(ValueError) as e: f(5)
    assert str(e.value) == 'bad path'
''',
        "hard", max_new_tokens=768),
    TaskSpec(
        "ipv4_to_int",
        "Write a Python function ipv4_to_int(s) that parses a strict dotted-quad "
        "IPv4 address and returns its 32-bit integer value. s must be a str "
        "consisting of exactly four parts separated by dots. Each part must be a "
        "run of ASCII decimal digits naming a value from 0 to 255, with no leading "
        "zero (except the single character 0), no sign, no spaces, and no empty "
        "part. Any violation, a non-string, or the wrong number of parts each -> "
        "ValueError('bad address'). The value is big-endian: the first part is the "
        "most significant byte, so 1.2.3.4 is 1 times 16777216 plus 2 times 65536 "
        "plus 3 times 256 plus 4, and 0.0.0.0 is 0 while 255.255.255.255 is "
        "4294967295. Output ONLY the function definition.",
        "solution.py",
        r'''def ipv4_to_int(s):
    if not isinstance(s, str):
        raise ValueError("bad address")
    parts = s.split(".")
    if len(parts) != 4:
        raise ValueError("bad address")
    val = 0
    for p in parts:
        if not p.isascii() or not p.isdigit():
            raise ValueError("bad address")
        if len(p) > 1 and p[0] == "0":
            raise ValueError("bad address")
        n = int(p)
        if n > 255:
            raise ValueError("bad address")
        val = val * 256 + n
    return val
''',
        r'''import pytest
from solution import ipv4_to_int as f
def test_zero(): assert f('0.0.0.0') == 0
def test_broadcast(): assert f('255.255.255.255') == 4294967295
def test_sequential(): assert f('1.2.3.4') == 16909060
def test_common(): assert f('192.168.0.1') == 3232235521
def test_ten(): assert f('10.0.0.1') == 167772161
def test_leading_zero():
    with pytest.raises(ValueError) as e: f('192.168.01.1')
    assert str(e.value) == 'bad address'
def test_too_big():
    with pytest.raises(ValueError): f('256.0.0.1')
def test_three_parts():
    with pytest.raises(ValueError): f('1.2.3')
def test_empty_part():
    with pytest.raises(ValueError): f('1..2.3')
def test_sign():
    with pytest.raises(ValueError): f('+1.2.3.4')
''',
        "hard", max_new_tokens=768),
    TaskSpec(
        "multiset_diff",
        "Write a Python function multiset_diff(a, b) that returns the multiset "
        "difference a minus b as a sorted list of integers. a and b are lists; "
        "every element of both must be an int and not a bool, and any other "
        "element -> ValueError('bad item'). Treat each list as a multiset (a bag "
        "that counts repetitions). For every distinct value, its count in the "
        "result is its count in a minus its count in b, but never below zero, so a "
        "value that appears three times in a and once in b appears twice in the "
        "result, and a value with more copies in b than in a does not appear at "
        "all. The returned list is sorted in ascending order. Output ONLY the "
        "function definition.",
        "solution.py",
        r'''def multiset_diff(a, b):
    from collections import Counter
    for lst in (a, b):
        for x in lst:
            if not isinstance(x, int) or isinstance(x, bool):
                raise ValueError("bad item")
    ca = Counter(a)
    cb = Counter(b)
    out = []
    for x in ca:
        rem = ca[x] - cb.get(x, 0)
        out.extend([x] * max(0, rem))
    return sorted(out)
''',
        r'''import pytest
from solution import multiset_diff as f
def test_basic(): assert f([1, 1, 2, 3], [1, 3]) == [1, 2]
def test_repeat(): assert f([1, 1, 1], [1]) == [1, 1]
def test_disjoint(): assert f([1, 2, 3], [4, 5]) == [1, 2, 3]
def test_all_removed(): assert f([1, 2], [1, 2, 3]) == []
def test_empty_a(): assert f([], [1]) == []
def test_sorted_out(): assert f([3, 1, 2, 2], []) == [1, 2, 2, 3]
def test_bad_item_bool():
    with pytest.raises(ValueError) as e: f([True], [])
    assert str(e.value) == 'bad item'
def test_bad_item_float():
    with pytest.raises(ValueError): f([1], [1.5])
''',
        "hard", max_new_tokens=768),
    TaskSpec(
        "parse_a1_ref",
        "Write a Python function parse_a1(ref) that parses a spreadsheet A1-style "
        "cell reference into a tuple (row, col) of 1-based integers. ref must be a "
        "non-empty str made of one or more uppercase ASCII letters (the column) "
        "immediately followed by one or more ASCII decimal digits (the row). The "
        "column letters use bijective base-26 numbering, so A is column 1, Z is "
        "26, AA is 27, AB is 28. The row is a positive decimal integer with no "
        "leading zero, so the smallest row is 1. Anything else, including a "
        "non-string, an empty string, a missing letter part, a missing digit "
        "part, a lowercase letter, a leading zero in the row, a zero row, or "
        "letters appearing after digits, each -> ValueError('bad ref'). The "
        "returned tuple lists the row first and the column second. Output ONLY the "
        "function definition.",
        "solution.py",
        r'''def parse_a1(ref):
    if not isinstance(ref, str) or ref == "":
        raise ValueError("bad ref")
    i, n = 0, len(ref)
    while i < n and "A" <= ref[i] <= "Z":
        i += 1
    if i == 0 or i == n:
        raise ValueError("bad ref")
    letters = ref[:i]
    digits = ref[i:]
    if not digits.isascii() or not digits.isdigit():
        raise ValueError("bad ref")
    if len(digits) > 1 and digits[0] == "0":
        raise ValueError("bad ref")
    row = int(digits)
    if row < 1:
        raise ValueError("bad ref")
    col = 0
    for ch in letters:
        col = col * 26 + (ord(ch) - 64)
    return (row, col)
''',
        r'''import pytest
from solution import parse_a1 as f
def test_a1(): assert f('A1') == (1, 1)
def test_b2(): assert f('B2') == (2, 2)
def test_z10(): assert f('Z10') == (10, 26)
def test_aa1(): assert f('AA1') == (1, 27)
def test_ab100(): assert f('AB100') == (100, 28)
def test_no_digits():
    with pytest.raises(ValueError) as e: f('AB')
    assert str(e.value) == 'bad ref'
def test_no_letters():
    with pytest.raises(ValueError): f('12')
def test_lowercase():
    with pytest.raises(ValueError): f('a1')
def test_leading_zero():
    with pytest.raises(ValueError): f('A01')
def test_zero_row():
    with pytest.raises(ValueError): f('A0')
def test_letters_after_digits():
    with pytest.raises(ValueError): f('A1B')
''',
        "hard", max_new_tokens=768),
    TaskSpec(
        "linked_cycle",
        "Write a Python function has_cycle(nxt) that detects whether following "
        "links from node 0 enters a cycle, returning a bool. nxt is a list where "
        "nxt[i] is the index of the node that node i points to, or -1 to mean it "
        "points to nothing. Every element must be an int and not a bool, and must "
        "be either -1 or a valid index from 0 up to len(nxt) minus 1; any other "
        "value -> ValueError('bad link'). Starting at node 0, repeatedly move to "
        "the node named by the current node's link. If a -1 link is reached the "
        "traversal ends with no cycle. If a node is visited a second time, the "
        "traversal is in a cycle. The empty list has no node 0 to start from and "
        "returns False. A node whose link points to itself is a cycle. Output ONLY "
        "the function definition.",
        "solution.py",
        r'''def has_cycle(nxt):
    for v in nxt:
        if not isinstance(v, int) or isinstance(v, bool):
            raise ValueError("bad link")
        if v < -1 or v >= len(nxt):
            raise ValueError("bad link")
    if not nxt:
        return False
    seen = set()
    cur = 0
    while cur != -1:
        if cur in seen:
            return True
        seen.add(cur)
        cur = nxt[cur]
    return False
''',
        r'''import pytest
from solution import has_cycle as f
def test_empty(): assert f([]) is False
def test_terminates(): assert f([-1]) is False
def test_self_loop(): assert f([0]) is True
def test_chain(): assert f([1, 2, -1]) is False
def test_cycle(): assert f([1, 2, 0]) is True
def test_unreached_end(): assert f([1, -1, 1]) is False
def test_reachable_cycle(): assert f([2, 2, 1]) is True
def test_out_of_range():
    with pytest.raises(ValueError) as e: f([5])
    assert str(e.value) == 'bad link'
def test_below_neg_one():
    with pytest.raises(ValueError): f([-2])
def test_bool():
    with pytest.raises(ValueError): f([True])
''',
        "hard", max_new_tokens=768),
    TaskSpec(
        "manhattan_tour",
        "Write a Python function tour_length(points) that returns the total "
        "Manhattan distance of visiting a sequence of grid points in order, as an "
        "int. points is a list; each element must be EXACTLY a tuple of exactly "
        "two values (x, y), each an int and not a bool; any element that is not "
        "such a tuple, or whose coordinates are not ints or are bools, -> "
        "ValueError('bad point'). The Manhattan distance between two points is the "
        "absolute difference of their x coordinates plus the absolute difference "
        "of their y coordinates. The tour length is the sum of the distances "
        "between each consecutive pair of points in the list. A list with fewer "
        "than two points has length 0. Output ONLY the function definition.",
        "solution.py",
        r'''def tour_length(points):
    for p in points:
        if type(p) is not tuple or len(p) != 2:
            raise ValueError("bad point")
        for v in p:
            if not isinstance(v, int) or isinstance(v, bool):
                raise ValueError("bad point")
    total = 0
    for i in range(1, len(points)):
        ax, ay = points[i - 1]
        bx, by = points[i]
        total += abs(bx - ax) + abs(by - ay)
    return total
''',
        r'''import pytest
from solution import tour_length as f
def test_pair(): assert f([(0, 0), (3, 4)]) == 7
def test_empty(): assert f([]) == 0
def test_single(): assert f([(1, 1)]) == 0
def test_l_shape(): assert f([(0, 0), (0, 5), (5, 5)]) == 10
def test_negative(): assert f([(0, 0), (-3, 0)]) == 3
def test_round_trip(): assert f([(0, 0), (1, 1), (0, 0)]) == 4
def test_bad_list():
    with pytest.raises(ValueError) as e: f([[0, 0]])
    assert str(e.value) == 'bad point'
def test_bad_len():
    with pytest.raises(ValueError): f([(0, 0, 0)])
def test_bool_coord():
    with pytest.raises(ValueError): f([(0, True)])
''',
        "hard", max_new_tokens=768),
    TaskSpec(
        "parse_kv_pairs",
        "Write a Python function parse_kv(s) that parses a semicolon-separated "
        "list of key-value assignments into a list of (key, value) tuples in "
        "order. s must be a str; otherwise -> ValueError('bad input'). The empty "
        "string returns the empty list. Otherwise split on semicolons; each item "
        "must contain exactly one equals sign that separates a non-empty key from "
        "a value. The key must be non-empty and consist only of ASCII letters, "
        "ASCII digits, and underscores; the value is the remainder and may be "
        "empty but must not contain a further equals sign. A duplicate key (one "
        "already seen earlier in the same string) -> ValueError('duplicate key'). "
        "Any malformed item (no equals sign, an empty key, a bad key character, a "
        "second equals sign, or an empty item from a stray semicolon) -> "
        "ValueError('bad item'). Output ONLY the function definition.",
        "solution.py",
        r'''def parse_kv(s):
    if not isinstance(s, str):
        raise ValueError("bad input")
    if s == "":
        return []
    out = []
    seen = set()
    for item in s.split(";"):
        if "=" not in item:
            raise ValueError("bad item")
        key, _, val = item.partition("=")
        if key == "":
            raise ValueError("bad item")
        for ch in key:
            if not (ch.isascii() and (ch.isalnum() or ch == "_")):
                raise ValueError("bad item")
        if "=" in val:
            raise ValueError("bad item")
        if key in seen:
            raise ValueError("duplicate key")
        seen.add(key)
        out.append((key, val))
    return out
''',
        r'''import pytest
from solution import parse_kv as f
def test_basic(): assert f('a=1;b=2') == [('a', '1'), ('b', '2')]
def test_empty(): assert f('') == []
def test_empty_value(): assert f('x=') == [('x', '')]
def test_underscore(): assert f('key_1=val') == [('key_1', 'val')]
def test_duplicate():
    with pytest.raises(ValueError) as e: f('a=1;a=2')
    assert str(e.value) == 'duplicate key'
def test_no_equals():
    with pytest.raises(ValueError) as e: f('a')
    assert str(e.value) == 'bad item'
def test_empty_key():
    with pytest.raises(ValueError): f('=v')
def test_two_equals():
    with pytest.raises(ValueError): f('a=b=c')
def test_trailing_semicolon():
    with pytest.raises(ValueError): f('a=1;')
def test_bad_key_char():
    with pytest.raises(ValueError): f('a b=1')
def test_bad_input():
    with pytest.raises(ValueError) as e: f(5)
    assert str(e.value) == 'bad input'
''',
        "hard", max_new_tokens=768),
    TaskSpec(
        "rotate_list",
        "Write a Python function rotate(items, k) that returns a NEW list equal to "
        "items rotated to the right by k positions, without mutating the input. "
        "items must be a list; otherwise -> ValueError('bad input'). k must be an "
        "int and not a bool; otherwise -> ValueError('bad shift'). A right "
        "rotation by k moves the last k elements to the front while preserving "
        "order, so rotating by 1 moves the final element to position 0. k is taken "
        "modulo the length, so a k equal to or larger than the length wraps "
        "around, and a negative k rotates to the left instead. Rotating the empty "
        "list gives the empty list. The input list object must be left unchanged. "
        "Output ONLY the function definition.",
        "solution.py",
        r'''def rotate(items, k):
    if not isinstance(items, list):
        raise ValueError("bad input")
    if not isinstance(k, int) or isinstance(k, bool):
        raise ValueError("bad shift")
    n = len(items)
    if n == 0:
        return []
    k %= n
    if k == 0:
        return list(items)
    return items[-k:] + items[:-k]
''',
        r'''import pytest
from solution import rotate as f
def test_basic(): assert f([1, 2, 3, 4, 5], 2) == [4, 5, 1, 2, 3]
def test_zero(): assert f([1, 2, 3], 0) == [1, 2, 3]
def test_full_wrap(): assert f([1, 2, 3], 3) == [1, 2, 3]
def test_over_wrap(): assert f([1, 2, 3], 4) == [3, 1, 2]
def test_negative(): assert f([1, 2, 3], -1) == [2, 3, 1]
def test_empty(): assert f([], 5) == []
def test_no_mutation():
    g = [1, 2, 3]
    f(g, 1)
    assert g == [1, 2, 3]
def test_bad_input():
    with pytest.raises(ValueError) as e: f('ab', 1)
    assert str(e.value) == 'bad input'
def test_bad_shift():
    with pytest.raises(ValueError) as e: f([1], True)
    assert str(e.value) == 'bad shift'
''',
        "hard", max_new_tokens=768),
    TaskSpec(
        "group_anagrams",
        "Write a Python function group_anagrams(words) that groups words that are "
        "anagrams of one another and returns a list of groups. words is a list; "
        "every element must be a str, and any non-string element -> "
        "ValueError('bad item'). Two words are anagrams when they contain exactly "
        "the same multiset of characters; the comparison is case sensitive, so an "
        "uppercase and lowercase letter are different characters. Within each "
        "group the words are sorted in ascending ASCII order, and a word that "
        "appears more than once appears that many times in its group. The groups "
        "themselves are ordered by the ascending ASCII order of their first "
        "(smallest) word. The empty list returns the empty list. Output ONLY the "
        "function definition.",
        "solution.py",
        r'''def group_anagrams(words):
    groups = {}
    for w in words:
        if not isinstance(w, str):
            raise ValueError("bad item")
        key = "".join(sorted(w))
        groups.setdefault(key, []).append(w)
    result = [sorted(g) for g in groups.values()]
    result.sort(key=lambda g: g[0])
    return result
''',
        r'''import pytest
from solution import group_anagrams as f
def test_basic():
    assert f(['eat', 'tea', 'tan', 'ate', 'nat', 'bat']) == [['ate', 'eat', 'tea'], ['bat'], ['nat', 'tan']]
def test_empty(): assert f([]) == []
def test_single(): assert f(['abc']) == [['abc']]
def test_repeat(): assert f(['a', 'b', 'a']) == [['a', 'a'], ['b']]
def test_case_sensitive(): assert f(['Ab', 'bA']) == [['Ab', 'bA']]
def test_two_groups(): assert f(['ba', 'ab', 'cd']) == [['ab', 'ba'], ['cd']]
def test_bad_item():
    with pytest.raises(ValueError) as e: f([1])
    assert str(e.value) == 'bad item'
''',
        "hard", max_new_tokens=768),
    TaskSpec(
        "stock_spans",
        "Write a Python function stock_spans(prices) that returns the list of "
        "stock spans for a sequence of daily prices. Each element of prices must "
        "be an int or a float but not a bool; any other element -> "
        "ValueError('bad price'). The span for a given day is the number of "
        "consecutive days ending at that day (including the day itself) on which "
        "the price was less than or equal to that day's price, walking backward "
        "and stopping at the first earlier day with a strictly greater price. So "
        "the span is always at least 1, equals the day index plus 1 when all "
        "earlier prices are less than or equal to today's, and equal prices "
        "extend the span. The empty list returns the empty list. Output ONLY the "
        "function definition.",
        "solution.py",
        r'''def stock_spans(prices):
    for p in prices:
        if isinstance(p, bool) or not isinstance(p, (int, float)):
            raise ValueError("bad price")
    spans = []
    stack = []
    for i, p in enumerate(prices):
        while stack and prices[stack[-1]] <= p:
            stack.pop()
        span = i + 1 if not stack else i - stack[-1]
        spans.append(span)
        stack.append(i)
    return spans
''',
        r'''import pytest
from solution import stock_spans as f
def test_classic(): assert f([100, 80, 60, 70, 60, 75, 85]) == [1, 1, 1, 2, 1, 4, 6]
def test_empty(): assert f([]) == []
def test_single(): assert f([10]) == [1]
def test_increasing(): assert f([10, 20, 30]) == [1, 2, 3]
def test_decreasing(): assert f([30, 20, 10]) == [1, 1, 1]
def test_equal(): assert f([5, 5, 5]) == [1, 2, 3]
def test_bad_price_bool():
    with pytest.raises(ValueError) as e: f([True])
    assert str(e.value) == 'bad price'
def test_bad_price_type():
    with pytest.raises(ValueError): f(['x'])
''',
        "hard", max_new_tokens=768),
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
