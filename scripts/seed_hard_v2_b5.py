#!/usr/bin/env python3
"""seed_hard_v2_b5.py - batch 5, second half of the batch-4 authoring wave
for the N>=100 hard-set lane (target ~60/100 together with b4).

Same contract as batches 1-4: soundness admission through task_curator gates;
difficulty screening against the served 14B is a later arm. Domains in this
file: ordering and canonicalization rules, small-parser semantics (escaping,
quoting), numeric edge semantics (rounding modes, overflow taxonomies), and
streaming/windowed aggregation. Doctrine unchanged: contract density over
textbook fame; every prompt states the full multi-clause contract in prose
and the hidden tests assert exact semantics including exact error messages
and exception types.
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
        "natural_sort_runs",
        "Write a Python function natural_sort(strings) returning a NEW list "
        "of the input strings ordered by natural comparison; the input list "
        "must not be mutated. Every element must be a str -> otherwise "
        "ValueError('bad item'). Comparison: each string is split into its "
        "maximal runs of ASCII digits 0-9 and runs of everything else, and "
        "strings compare run by run from the left. When both runs are digit "
        "runs they compare by NUMERIC value (so 'x2' sorts before 'x10'). "
        "When both are non-digit runs they compare as ordinary "
        "case-sensitive strings. When a digit run meets a non-digit run, the "
        "digit run sorts FIRST. If every compared run is equal and one "
        "string runs out of runs first, the shorter one sorts first. If the "
        "run sequences are entirely equal (which can happen when digit runs "
        "differ only in leading zeros, like 'a01' versus 'a1'), the final "
        "tie-break is ordinary string comparison ascending. Empty input "
        "returns []. Output ONLY the function definition.",
        "solution.py",
        r'''def natural_sort(strings):
    import re
    for s in strings:
        if not isinstance(s, str):
            raise ValueError("bad item")
    def key(s):
        runs = []
        for m in re.finditer(r"[0-9]+|[^0-9]+", s):
            t = m.group(0)
            if t[0] in "0123456789":
                runs.append((0, int(t), ""))
            else:
                runs.append((1, 0, t))
        return (runs, s)
    return sorted(strings, key=key)
''',
        r'''import pytest
from solution import natural_sort as f
def test_numeric(): assert f(['x10', 'x2', 'x1']) == ['x1', 'x2', 'x10']
def test_leading_zero_tiebreak(): assert f(['a1', 'a01']) == ['a01', 'a1']
def test_mixed(): assert f(['b', 'a10', 'a2', 'a']) == ['a', 'a2', 'a10', 'b']
def test_prefix_text(): assert f(['aa', 'a1']) == ['a1', 'aa']
def test_digit_before_text(): assert f(['a', '1']) == ['1', 'a']
def test_infix(): assert f(['a10b', 'a2b']) == ['a2b', 'a10b']
def test_empty(): assert f([]) == []
def test_no_mutation():
    g = ['b', 'a']
    assert f(g) == ['a', 'b']
    assert g == ['b', 'a']
def test_bad_item():
    with pytest.raises(ValueError) as e: f(['a', 3])
    assert str(e.value) == 'bad item'
''',
        "hard", max_new_tokens=768),
    TaskSpec(
        "posix_path_normalize",
        "Write a Python function normalize_path(p) that normalizes a "
        "POSIX-style path string purely lexically and returns the canonical "
        "form. Rules: runs of consecutive slashes collapse to one (including "
        "a leading '//' which becomes a single '/'); '.' segments are "
        "removed; a '..' segment removes the preceding real segment when one "
        "exists. The path is ABSOLUTE when it starts with '/': then '..' at "
        "the top is silently dropped (you cannot go above the root). A "
        "RELATIVE path instead accumulates leading '..' segments that have "
        "nothing left to remove (they must survive in the output, and a '..' "
        "never removes another '..'). The result never has a trailing slash "
        "unless it is exactly '/'. A relative path that normalizes to "
        "nothing returns '.', and the empty string input returns '.'. "
        "Examples: 'a/b/../c' gives 'a/c'; '/../x' gives '/x'; 'a/../../b' "
        "gives '../b'; '//a/b' gives '/a/b'. Output ONLY the function "
        "definition.",
        "solution.py",
        r'''def normalize_path(p):
    absolute = p.startswith("/")
    parts = []
    for seg in p.split("/"):
        if seg == "" or seg == ".":
            continue
        if seg == "..":
            if parts and parts[-1] != "..":
                parts.pop()
            elif not absolute:
                parts.append("..")
        else:
            parts.append(seg)
    body = "/".join(parts)
    if absolute:
        return "/" + body
    return body if body else "."
''',
        r'''from solution import normalize_path as f
def test_dotdot(): assert f('a/b/../c') == 'a/c'
def test_above_root(): assert f('/../x') == '/x'
def test_collapse(): assert f('a/./b//c/') == 'a/b/c'
def test_keep_leading_dotdot(): assert f('../..//a') == '../../a'
def test_empties_to_dot(): assert f('a/..') == '.'
def test_root(): assert f('/') == '/'
def test_empty(): assert f('') == '.'
def test_mixed_updirs(): assert f('a/../../b') == '../b'
def test_double_leading_slash(): assert f('//a/b') == '/a/b'
def test_absolute_tail(): assert f('/a/b/..') == '/a'
''',
        "hard", max_new_tokens=768),
    TaskSpec(
        "rank_scores_two_modes",
        "Write a Python function rank_scores(scores, mode) returning the "
        "list of ranks of integer scores, aligned index by index with the "
        "input, where HIGHER scores get better (smaller) ranks. mode must be "
        "the string 'competition' or 'dense' -> otherwise ValueError('bad "
        "mode'), and this check happens before any score validation. Every "
        "score must be an int and not a bool -> otherwise ValueError('bad "
        "score'). In 'competition' mode a score's rank is 1 plus the number "
        "of STRICTLY greater scores in the list (ties share a rank and the "
        "following rank numbers are skipped: scores 50, 30, 50, 20 rank as "
        "1, 3, 1, 4). In 'dense' mode a score's rank is 1 plus the number "
        "of DISTINCT strictly greater values (no skipping: the same scores "
        "rank 1, 2, 1, 3). The input list must not be mutated and the "
        "empty list returns []. Output ONLY the function definition.",
        "solution.py",
        r'''def rank_scores(scores, mode):
    if mode not in ("competition", "dense"):
        raise ValueError("bad mode")
    for s in scores:
        if not isinstance(s, int) or isinstance(s, bool):
            raise ValueError("bad score")
    uniq = sorted(set(scores), reverse=True)
    if mode == "dense":
        r = {s: i + 1 for i, s in enumerate(uniq)}
    else:
        r = {}
        seen = 0
        for s in uniq:
            r[s] = seen + 1
            seen += scores.count(s)
    return [r[s] for s in scores]
''',
        r'''import pytest
from solution import rank_scores as f
def test_competition(): assert f([50, 30, 50, 20], 'competition') == [1, 3, 1, 4]
def test_dense(): assert f([50, 30, 50, 20], 'dense') == [1, 2, 1, 3]
def test_all_tied(): assert f([5, 5, 5], 'competition') == [1, 1, 1]
def test_empty(): assert f([], 'dense') == []
def test_ascending_input(): assert f([1, 2, 3], 'competition') == [3, 2, 1]
def test_negative(): assert f([-1, -2], 'dense') == [1, 2]
def test_bad_mode():
    with pytest.raises(ValueError) as e: f([1], 'standard')
    assert str(e.value) == 'bad mode'
def test_mode_checked_first():
    with pytest.raises(ValueError) as e: f([True], 'standard')
    assert str(e.value) == 'bad mode'
def test_bad_score():
    with pytest.raises(ValueError) as e: f([True], 'dense')
    assert str(e.value) == 'bad score'
''',
        "hard", max_new_tokens=768),
    TaskSpec(
        "query_pairs_decode",
        "Write a Python function parse_qs_pairs(s) that parses a URL query "
        "string into an ordered list of (key, value) string tuples. The "
        "string is split on '&'; empty segments (from leading, trailing, or "
        "doubled ampersands) are silently skipped. Each remaining segment "
        "must contain at least one '=' -> otherwise ValueError('no equals'); "
        "the segment splits at its FIRST '=' only, so later equal signs "
        "belong to the value. A segment whose part before the '=' is empty "
        "-> ValueError('empty key'). Both key and value are then decoded "
        "independently: '+' becomes a space; '%' followed by exactly two "
        "hex digits (either case) becomes the character with that code "
        "point; a '%' NOT followed by two hex digits -> ValueError('bad "
        "percent'). Decoding scans left to right and a decoded character is "
        "never re-examined (so '%2B' yields a literal '+', not a space). "
        "Segments are processed left to right and errors report the first "
        "problem encountered. The empty string returns []. Output ONLY the "
        "function definition.",
        "solution.py",
        r'''def parse_qs_pairs(s):
    def dec(t):
        out = []
        i = 0
        while i < len(t):
            c = t[i]
            if c == "+":
                out.append(" ")
                i += 1
            elif c == "%":
                h = t[i + 1:i + 3]
                if len(h) != 2 or any(x not in "0123456789abcdefABCDEF" for x in h):
                    raise ValueError("bad percent")
                out.append(chr(int(h, 16)))
                i += 3
            else:
                out.append(c)
                i += 1
        return "".join(out)
    pairs = []
    for seg in s.split("&"):
        if seg == "":
            continue
        if "=" not in seg:
            raise ValueError("no equals")
        k, _, v = seg.partition("=")
        if k == "":
            raise ValueError("empty key")
        pairs.append((dec(k), dec(v)))
    return pairs
''',
        r'''import pytest
from solution import parse_qs_pairs as f
def test_two_pairs(): assert f('a=1&b=2') == [('a', '1'), ('b', '2')]
def test_plus_and_percent(): assert f('a+b=c%26d') == [('a b', 'c&d')]
def test_no_double_decode(): assert f('a=%2B') == [('a', '+')]
def test_first_equals(): assert f('a=b=c') == [('a', 'b=c')]
def test_skip_empty_segments(): assert f('a=1&&b=2') == [('a', '1'), ('b', '2')]
def test_empty(): assert f('') == []
def test_empty_value(): assert f('a=') == [('a', '')]
def test_key_decoded(): assert f('%41=x') == [('A', 'x')]
def test_bad_percent():
    with pytest.raises(ValueError) as e: f('a=%zz')
    assert str(e.value) == 'bad percent'
def test_short_percent():
    with pytest.raises(ValueError): f('a=%2')
def test_no_equals():
    with pytest.raises(ValueError) as e: f('abc')
    assert str(e.value) == 'no equals'
def test_empty_key():
    with pytest.raises(ValueError) as e: f('=x')
    assert str(e.value) == 'empty key'
''',
        "hard", max_new_tokens=768),
    TaskSpec(
        "hash_comment_strip",
        "Write a Python function strip_comments(src) that removes '#' line "
        "comments from source-like text while respecting string literals, "
        "and returns the transformed text. The text is processed line by "
        "line ('\\n' separated); the line structure is preserved exactly (the "
        "output has the same number of lines). On each line, characters are "
        "scanned left to right. Outside any string literal, a '#' starts a "
        "comment: the '#' and everything after it on that line are dropped, "
        "and any spaces or tabs immediately before the dropped comment are "
        "also removed; trailing whitespace on lines WITHOUT a comment is "
        "preserved untouched. A single quote or double quote opens a string "
        "literal, closed only by the same quote character; the other quote "
        "character and '#' are ordinary characters inside it. Inside a "
        "string literal a backslash escapes the next character (so an "
        "escaped quote does not close the literal); the backslash and the "
        "escaped character are both kept in the output. Outside string "
        "literals a backslash is an ordinary character with no special "
        "meaning. String literals do NOT span lines: a literal still open "
        "at the end of its line -> ValueError('unterminated string'), and a "
        "backslash as the last character of a line while inside a literal "
        "is likewise unterminated. Output ONLY the function definition.",
        "solution.py",
        r'''def strip_comments(src):
    out_lines = []
    for line in src.split("\n"):
        res = []
        q = None
        i = 0
        n = len(line)
        cut = False
        while i < n:
            c = line[i]
            if q is None:
                if c == "#":
                    cut = True
                    break
                res.append(c)
                if c == "\"" or c == "'":
                    q = c
                i += 1
            else:
                res.append(c)
                if c == "\\":
                    if i + 1 >= n:
                        raise ValueError("unterminated string")
                    res.append(line[i + 1])
                    i += 2
                    continue
                if c == q:
                    q = None
                i += 1
        if q is not None:
            raise ValueError("unterminated string")
        text = "".join(res)
        if cut:
            text = text.rstrip(" \t")
        out_lines.append(text)
    return "\n".join(out_lines)
''',
        r'''import pytest
from solution import strip_comments as f
def test_plain(): assert f('a = 1 # note') == 'a = 1'
def test_hash_in_double(): assert f('s = "x # y" # real') == 's = "x # y"'
def test_hash_in_single(): assert f("m = 'a # b' # c") == "m = 'a # b'"
def test_escaped_quote(): assert f('y = "a\\"b" # c') == 'y = "a\\"b"'
def test_lines_preserved(): assert f('a # x\n# y\nb') == 'a\n\nb'
def test_no_comment_keeps_trailing(): assert f('a   ') == 'a   '
def test_backslash_outside(): assert f('x\\y # c') == 'x\\y'
def test_unterminated():
    with pytest.raises(ValueError) as e: f('x = "abc')
    assert str(e.value) == 'unterminated string'
def test_trailing_backslash_in_string():
    with pytest.raises(ValueError) as e: f('x = "ab\\')
    assert str(e.value) == 'unterminated string'
''',
        "hard", max_new_tokens=768),
    TaskSpec(
        "json_pointer_get",
        "Write a Python function jp_get(doc, pointer) that evaluates an RFC "
        "6901 JSON Pointer against a document of nested dicts, lists, and "
        "scalars, returning the referenced value. The empty pointer '' "
        "returns the whole document. Any other pointer must start with '/' "
        "-> otherwise ValueError('bad pointer'). The pointer splits on '/' "
        "into reference tokens (an empty token is a legal token naming the "
        "empty-string dict key). Each token is unescaped by scanning left "
        "to right: the two-character sequence '~1' yields '/', '~0' yields "
        "'~', and a '~' followed by anything else (or ending the token) -> "
        "ValueError('bad pointer'). The unescape never rescans produced "
        "characters: the raw token '~01' unescapes to the two characters "
        "'~1', not to '/'. Navigation per token: in a dict the unescaped "
        "token must be a present key -> otherwise ValueError('not found'). "
        "In a list the token must be ASCII digits with no leading zero "
        "(except exactly '0'); '-' or anything else non-conforming -> "
        "ValueError('bad index'); a conforming index at or past the list "
        "length -> ValueError('not found'). Stepping into any non-dict "
        "non-list value -> ValueError('not found'). Output ONLY the "
        "function definition.",
        "solution.py",
        r'''def jp_get(doc, pointer):
    if pointer == "":
        return doc
    if not pointer.startswith("/"):
        raise ValueError("bad pointer")
    cur = doc
    for raw in pointer.split("/")[1:]:
        buf = []
        i = 0
        while i < len(raw):
            c = raw[i]
            if c == "~":
                if i + 1 >= len(raw) or raw[i + 1] not in "01":
                    raise ValueError("bad pointer")
                buf.append("/" if raw[i + 1] == "1" else "~")
                i += 2
            else:
                buf.append(c)
                i += 1
        token = "".join(buf)
        if isinstance(cur, dict):
            if token not in cur:
                raise ValueError("not found")
            cur = cur[token]
        elif isinstance(cur, list):
            if not (token.isascii() and token.isdigit()) or (len(token) > 1 and token[0] == "0"):
                raise ValueError("bad index")
            idx = int(token)
            if idx >= len(cur):
                raise ValueError("not found")
            cur = cur[idx]
        else:
            raise ValueError("not found")
    return cur
''',
        r'''import pytest
from solution import jp_get as f
def test_nested(): assert f({'a': {'b': [10, 20]}}, '/a/b/1') == 20
def test_whole_doc(): assert f(5, '') == 5
def test_empty_key(): assert f({'': {'x': 1}}, '//x') == 1
def test_tilde1(): assert f({'a/b': 1}, '/a~1b') == 1
def test_no_rescan(): assert f({'~1': 1}, '/~01') == 1
def test_missing_slash():
    with pytest.raises(ValueError) as e: f({}, 'a')
    assert str(e.value) == 'bad pointer'
def test_bad_escape():
    with pytest.raises(ValueError) as e: f({}, '/~2')
    assert str(e.value) == 'bad pointer'
def test_leading_zero_index():
    with pytest.raises(ValueError) as e: f([1], '/01')
    assert str(e.value) == 'bad index'
def test_dash_index():
    with pytest.raises(ValueError) as e: f([1], '/-')
    assert str(e.value) == 'bad index'
def test_index_out_of_range():
    with pytest.raises(ValueError) as e: f([1], '/5')
    assert str(e.value) == 'not found'
def test_step_into_scalar():
    with pytest.raises(ValueError) as e: f(3, '/a')
    assert str(e.value) == 'not found'
''',
        "hard", max_new_tokens=768),
    TaskSpec(
        "decimal_string_add",
        "Write a Python function add_decimals(a, b) that adds two decimal "
        "number strings EXACTLY (no floating point anywhere) and returns the "
        "sum as a canonical decimal string. Input grammar for each operand: "
        "an optional single leading '-' (no '+'), then one or more digits, "
        "then optionally a '.' followed by one or more digits; digits are "
        "required on BOTH sides of the dot, so '.5' and '5.' are invalid. "
        "No exponent, no separators, no whitespace. Any violation -> "
        "ValueError('bad number'). Leading zeros in inputs are tolerated. "
        "Canonical output: no '+' ever; trailing zeros of the fraction are "
        "stripped and the dot is omitted when the fraction empties; the "
        "integer part has no leading zeros (a single '0' when the integer "
        "part is zero); an all-zero result is exactly '0', never '-0'. "
        "Values of any magnitude must stay exact (hundreds of digits). "
        "Examples: '0.1' plus '0.2' is '0.3'; '1.05' plus '-0.05' is '1'; "
        "'-2' plus '2' is '0'. Output ONLY the function definition.",
        "solution.py",
        r'''def add_decimals(a, b):
    import re
    def parse(s):
        m = re.fullmatch(r"(-?)(\d+)(?:\.(\d+))?", s)
        if not m:
            raise ValueError("bad number")
        return (-1 if m.group(1) else 1), m.group(2), (m.group(3) or "")
    s1, i1, f1 = parse(a)
    s2, i2, f2 = parse(b)
    scale = max(len(f1), len(f2))
    v1 = s1 * int(i1 + f1.ljust(scale, "0"))
    v2 = s2 * int(i2 + f2.ljust(scale, "0"))
    total = v1 + v2
    if total == 0:
        return "0"
    digits = str(abs(total)).rjust(scale + 1, "0")
    if scale:
        whole, frac = digits[:-scale], digits[-scale:]
        frac = frac.rstrip("0")
    else:
        whole, frac = digits, ""
    whole = whole.lstrip("0") or "0"
    sign = "-" if total < 0 else ""
    return sign + whole + ("." + frac if frac else "")
''',
        r'''import pytest
from solution import add_decimals as f
def test_tenths(): assert f('0.1', '0.2') == '0.3'
def test_strip_dot(): assert f('1.05', '-0.05') == '1'
def test_mixed_scale(): assert f('-1.5', '0.25') == '-1.25'
def test_carry(): assert f('999', '1') == '1000'
def test_zero(): assert f('-2', '2') == '0'
def test_input_leading_zeros(): assert f('007', '0.0') == '7'
def test_big(): assert f('12345678901234567890.1', '0.9') == '12345678901234567891'
def test_bare_dot_fraction():
    with pytest.raises(ValueError) as e: f('.5', '1')
    assert str(e.value) == 'bad number'
def test_exponent():
    with pytest.raises(ValueError): f('1e3', '1')
def test_plus_sign():
    with pytest.raises(ValueError): f('+1', '1')
''',
        "hard", max_new_tokens=768),
    TaskSpec(
        "round_to_multiple_modes",
        "Write a Python function round_multiple(n, m, mode) that rounds the "
        "integer n to a multiple of the positive integer m under an explicit "
        "rounding mode, entirely in integer arithmetic. Validation order: n "
        "must be an int and not a bool -> ValueError('bad value'); m must "
        "be an int, not a bool, and at least 1 -> ValueError('bad step'); "
        "mode must be one of the strings 'floor', 'ceil', 'half_up', "
        "'half_even' -> ValueError('bad mode'). An n that is already a "
        "multiple of m is returned unchanged in every mode. Modes: 'floor' "
        "gives the largest multiple <= n (toward negative infinity, so -7 "
        "with step 4 gives -8); 'ceil' gives the smallest multiple >= n; "
        "'half_up' gives the nearest multiple, with exact halfway ties "
        "going AWAY from zero (6 with step 4 gives 8, -6 gives -8); "
        "'half_even' gives the nearest multiple, with ties going to the "
        "multiple whose quotient by m is even (6 with step 4 gives 8 since "
        "8 is 2 times 4; 2 with step 4 gives 0). Results must be exact for "
        "arbitrarily large integers. Output ONLY the function definition.",
        "solution.py",
        r'''def round_multiple(n, m, mode):
    if not isinstance(n, int) or isinstance(n, bool):
        raise ValueError("bad value")
    if not isinstance(m, int) or isinstance(m, bool) or m < 1:
        raise ValueError("bad step")
    if mode not in ("floor", "ceil", "half_up", "half_even"):
        raise ValueError("bad mode")
    q, r = divmod(n, m)
    if r == 0:
        return n
    if mode == "floor":
        return q * m
    if mode == "ceil":
        return (q + 1) * m
    lo, hi = q * m, (q + 1) * m
    if 2 * r < m:
        return lo
    if 2 * r > m:
        return hi
    if mode == "half_up":
        return hi if n > 0 else lo
    return lo if q % 2 == 0 else hi
''',
        r'''import pytest
from solution import round_multiple as f
def test_floor_pos(): assert f(7, 4, 'floor') == 4
def test_floor_neg(): assert f(-7, 4, 'floor') == -8
def test_ceil_pos(): assert f(7, 4, 'ceil') == 8
def test_ceil_neg(): assert f(-7, 4, 'ceil') == -4
def test_half_up_tie(): assert f(6, 4, 'half_up') == 8
def test_half_up_tie_neg(): assert f(-6, 4, 'half_up') == -8
def test_half_even_tie_odd_q(): assert f(6, 4, 'half_even') == 8
def test_half_even_tie_even_q(): assert f(2, 4, 'half_even') == 0
def test_below_half(): assert f(5, 4, 'half_up') == 4
def test_exact_multiple(): assert f(8, 4, 'half_even') == 8
def test_bad_mode():
    with pytest.raises(ValueError) as e: f(1, 2, 'up')
    assert str(e.value) == 'bad mode'
def test_bad_step():
    with pytest.raises(ValueError) as e: f(1, 0, 'floor')
    assert str(e.value) == 'bad step'
def test_bad_value():
    with pytest.raises(ValueError) as e: f(True, 2, 'floor')
    assert str(e.value) == 'bad value'
''',
        "hard", max_new_tokens=768),
    TaskSpec(
        "bounded_int_parse",
        "Write a Python function parse_bounded(s, bits) that parses a "
        "decimal integer string and range-checks it against a signed "
        "two's-complement width, distinguishing syntax errors from range "
        "errors by EXCEPTION TYPE. bits must be an int, not a bool, and at "
        "least 1 -> otherwise ValueError('bad bits'). Syntax: an optional "
        "single leading '-' followed by one or more ASCII digits, with no "
        "leading zeros unless the digits are exactly '0'; additionally the "
        "exact string '-0' is invalid. No '+', no whitespace, no other "
        "characters. Any syntax violation -> ValueError('bad int'). A "
        "syntactically valid value outside the inclusive range from "
        "-(2**(bits-1)) to 2**(bits-1)-1 -> OverflowError('out of range') "
        "(note: OverflowError, NOT ValueError; tests distinguish the two "
        "types). In range, return the parsed int. bits equal to 1 is legal "
        "with range -1..0. Output ONLY the function definition.",
        "solution.py",
        r'''def parse_bounded(s, bits):
    if not isinstance(bits, int) or isinstance(bits, bool) or bits < 1:
        raise ValueError("bad bits")
    import re
    if not re.fullmatch(r"-?(0|[1-9][0-9]*)", s) or s == "-0":
        raise ValueError("bad int")
    v = int(s)
    if v < -(2 ** (bits - 1)) or v > 2 ** (bits - 1) - 1:
        raise OverflowError("out of range")
    return v
''',
        r'''import pytest
from solution import parse_bounded as f
def test_min(): assert f('-128', 8) == -128
def test_max(): assert f('127', 8) == 127
def test_over():
    with pytest.raises(OverflowError) as e: f('128', 8)
    assert str(e.value) == 'out of range'
def test_under():
    with pytest.raises(OverflowError): f('-129', 8)
def test_one_bit(): assert f('0', 1) == 0 and f('-1', 1) == -1
def test_one_bit_over():
    with pytest.raises(OverflowError): f('1', 1)
def test_overflow_is_not_valueerror():
    try:
        f('999', 4)
    except ValueError:
        assert False
    except OverflowError:
        pass
def test_leading_zeros():
    with pytest.raises(ValueError) as e: f('007', 8)
    assert str(e.value) == 'bad int'
def test_minus_zero():
    with pytest.raises(ValueError): f('-0', 8)
def test_plus():
    with pytest.raises(ValueError): f('+1', 8)
def test_space():
    with pytest.raises(ValueError): f(' 1', 8)
def test_bad_bits():
    with pytest.raises(ValueError) as e: f('1', 0)
    assert str(e.value) == 'bad bits'
''',
        "hard", max_new_tokens=768),
    TaskSpec(
        "session_windows",
        "Write a Python function sessionize(events, gap) that groups event "
        "timestamps into per-user sessions and returns a dict mapping each "
        "user to the list of their session sizes. gap must be an int, not a "
        "bool, and at least 0 -> otherwise ValueError('bad gap'). events is "
        "a list; each element must be EXACTLY a tuple of exactly two values "
        "(user, timestamp) with user a str and timestamp an int and not a "
        "bool -> otherwise ValueError('bad event'). Events may arrive in "
        "any order and interleaved across users. Per user, the timestamps "
        "are sorted ascending (duplicates allowed); a new session starts at "
        "the first timestamp and whenever a timestamp exceeds its "
        "predecessor by MORE than gap (a difference exactly equal to gap "
        "stays in the same session, so with gap 0 duplicate timestamps "
        "share a session but a difference of 1 splits). Each session's size "
        "is its event count. The returned dict lists users in order of "
        "their FIRST appearance in the input. The input list must not be "
        "mutated. An empty list returns {}. Output ONLY the function "
        "definition.",
        "solution.py",
        r'''def sessionize(events, gap):
    if not isinstance(gap, int) or isinstance(gap, bool) or gap < 0:
        raise ValueError("bad gap")
    order = []
    times = {}
    for ev in events:
        if type(ev) is not tuple or len(ev) != 2:
            raise ValueError("bad event")
        user, ts = ev
        if not isinstance(user, str) or not isinstance(ts, int) or isinstance(ts, bool):
            raise ValueError("bad event")
        if user not in times:
            times[user] = []
            order.append(user)
        times[user].append(ts)
    out = {}
    for user in order:
        stamps = sorted(times[user])
        sizes = []
        for i, t in enumerate(stamps):
            if i == 0 or t - stamps[i - 1] > gap:
                sizes.append(1)
            else:
                sizes[-1] += 1
        out[user] = sizes
    return out
''',
        r'''import pytest
from solution import sessionize as f
def test_split(): assert f([('a', 1), ('a', 2), ('a', 10)], 3) == {'a': [2, 1]}
def test_unordered_and_key_order():
    r = f([('a', 10), ('b', 1), ('a', 1)], 9)
    assert r == {'a': [2], 'b': [1]}
    assert list(r) == ['a', 'b']
def test_duplicate_ts_gap0(): assert f([('a', 5), ('a', 5)], 0) == {'a': [2]}
def test_gap0_splits_on_1(): assert f([('a', 1), ('a', 2)], 0) == {'a': [1, 1]}
def test_empty(): assert f([], 5) == {}
def test_no_mutation():
    e = [('a', 2), ('a', 1)]
    f(e, 0)
    assert e == [('a', 2), ('a', 1)]
def test_bad_gap():
    with pytest.raises(ValueError) as e: f([], -1)
    assert str(e.value) == 'bad gap'
def test_bool_ts():
    with pytest.raises(ValueError) as e: f([('a', True)], 5)
    assert str(e.value) == 'bad event'
def test_list_event():
    with pytest.raises(ValueError): f([['a', 1]], 5)
''',
        "hard", max_new_tokens=768),
    TaskSpec(
        "top_k_first_seen",
        "Write a Python function top_k(items, k) returning the k most "
        "frequent items of a list, most frequent first. k must be an int, "
        "not a bool, and at least 0 -> otherwise ValueError('bad k'). "
        "Ordering: primary key is the count, descending; items with EQUAL "
        "counts order by their FIRST occurrence position in the input, "
        "earlier first. Each qualifying item appears exactly once in the "
        "result. If k is 0 the result is []; if k exceeds the number of "
        "distinct items, all distinct items are returned under the same "
        "ordering. The input list must not be mutated. An empty list "
        "returns [] for any valid k. Output ONLY the function definition.",
        "solution.py",
        r'''def top_k(items, k):
    if not isinstance(k, int) or isinstance(k, bool) or k < 0:
        raise ValueError("bad k")
    counts = {}
    first = {}
    for i, x in enumerate(items):
        if x not in counts:
            counts[x] = 0
            first[x] = i
        counts[x] += 1
    ranked = sorted(counts, key=lambda x: (-counts[x], first[x]))
    return ranked[:k]
''',
        r'''import pytest
from solution import top_k as f
def test_tie_first_seen(): assert f(['b', 'a', 'b', 'a', 'c'], 2) == ['b', 'a']
def test_frequency_wins(): assert f([3, 3, 1, 1, 1], 1) == [1]
def test_empty(): assert f([], 3) == []
def test_k_zero(): assert f(['x'], 0) == []
def test_k_exceeds(): assert f(['x', 'y'], 9) == ['x', 'y']
def test_three_way(): assert f([1, 2, 2, 1, 3], 3) == [1, 2, 3]
def test_no_mutation():
    g = [2, 1, 2]
    f(g, 1)
    assert g == [2, 1, 2]
def test_negative_k():
    with pytest.raises(ValueError) as e: f([], -1)
    assert str(e.value) == 'bad k'
def test_bool_k():
    with pytest.raises(ValueError): f([], True)
''',
        "hard", max_new_tokens=768),
    TaskSpec(
        "chunk_reassemble",
        "Write a Python function reassemble(chunks) that rebuilds a message "
        "from out-of-order transport chunks and returns the assembled "
        "string. chunks is a list; each element must be EXACTLY a tuple of "
        "exactly two values (seq, data) with seq an int, not a bool, and at "
        "least 0, and data a str -> otherwise ValueError('bad chunk'). "
        "Chunks are validated in list order. A repeated sequence number is "
        "legal ONLY when its data is identical to what was already seen for "
        "that number; a disagreeing duplicate -> ValueError('conflict'), "
        "reported during the scan (so a conflict is reported even when the "
        "stream also has missing chunks). After the scan, the collected "
        "sequence numbers must be exactly 0 through the maximum with no "
        "holes; any missing number -> ValueError('gap'). Return the data "
        "strings concatenated in sequence order; empty-string data chunks "
        "are legal. An empty chunk list returns ''. Output ONLY the "
        "function definition.",
        "solution.py",
        r'''def reassemble(chunks):
    seen = {}
    for ch in chunks:
        if type(ch) is not tuple or len(ch) != 2:
            raise ValueError("bad chunk")
        seq, data = ch
        if not isinstance(seq, int) or isinstance(seq, bool) or seq < 0:
            raise ValueError("bad chunk")
        if not isinstance(data, str):
            raise ValueError("bad chunk")
        if seq in seen:
            if seen[seq] != data:
                raise ValueError("conflict")
        else:
            seen[seq] = data
    if not seen:
        return ""
    top = max(seen)
    if set(seen) != set(range(top + 1)):
        raise ValueError("gap")
    return "".join(seen[i] for i in range(top + 1))
''',
        r'''import pytest
from solution import reassemble as f
def test_out_of_order(): assert f([(1, 'b'), (0, 'a'), (2, 'c')]) == 'abc'
def test_empty(): assert f([]) == ''
def test_agreeing_duplicate(): assert f([(0, 'x'), (0, 'x')]) == 'x'
def test_empty_data_chunk(): assert f([(0, ''), (1, 'z')]) == 'z'
def test_conflict():
    with pytest.raises(ValueError) as e: f([(0, 'x'), (0, 'y')])
    assert str(e.value) == 'conflict'
def test_gap():
    with pytest.raises(ValueError) as e: f([(0, 'a'), (2, 'c')])
    assert str(e.value) == 'gap'
def test_conflict_beats_gap():
    with pytest.raises(ValueError) as e: f([(0, 'a'), (0, 'b'), (3, 'd')])
    assert str(e.value) == 'conflict'
def test_negative_seq():
    with pytest.raises(ValueError) as e: f([(-1, 'a')])
    assert str(e.value) == 'bad chunk'
def test_int_data():
    with pytest.raises(ValueError): f([(0, 5)])
def test_list_chunk():
    with pytest.raises(ValueError): f([[0, 'a']])
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
