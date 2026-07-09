#!/usr/bin/env python3
"""seed_hard_v2_b4.py - batch 4 for the N>=100 hard-set lane (target ~60/100).

Same contract as batches 1-3: soundness admission through task_curator gates;
difficulty screening against the served 14B is a later arm. Batch 4 doctrine:
contract density over textbook fame. Every task is a multi-clause prose
contract (edge-case behavior, error taxonomies, tie-breaking, canonical
ordering) rather than a famous algorithm. Domains in this file: text and
tokenization contracts, interval and geometry arithmetic, state-machine
simulation, data validation with precise error taxonomies. The second half of
the authoring wave (ordering, small parsers, numeric edges, streaming) lives
in seed_hard_v2_b5.py to keep each file reviewable.
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
        "word_wrap_greedy",
        "Write a Python function wrap_text(s, width) that greedily wraps text "
        "into lines and returns them as a list of strings. Words are maximal "
        "runs of non-whitespace characters; any run of whitespace (spaces, "
        "tabs, newlines) separates words and is never preserved. width must be "
        "an int and must not be a bool, and must be at least 1; otherwise "
        "-> ValueError('bad width'). Greedy packing: words are placed on the "
        "current line joined by single spaces as long as the line stays within "
        "width characters; a word that does not fit starts a new line. A word "
        "longer than width is handled specially: the current line (if any) is "
        "finished first, then the word is cut into consecutive pieces of "
        "exactly width characters, each full piece becoming its own line, and "
        "the final remainder (between 1 and width characters) starts a new "
        "current line that later words may still join. Returned lines never "
        "have leading or trailing spaces and are never empty. An empty or "
        "all-whitespace input returns []. Output ONLY the function definition.",
        "solution.py",
        r'''def wrap_text(s, width):
    if not isinstance(width, int) or isinstance(width, bool) or width < 1:
        raise ValueError("bad width")
    lines = []
    cur = ""
    for w in s.split():
        while len(w) > width:
            if cur:
                lines.append(cur)
                cur = ""
            lines.append(w[:width])
            w = w[width:]
        if not cur:
            cur = w
        elif len(cur) + 1 + len(w) <= width:
            cur = cur + " " + w
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines
''',
        r'''import pytest
from solution import wrap_text as f
def test_greedy(): assert f('the quick brown fox', 10) == ['the quick', 'brown fox']
def test_exact_fit(): assert f('aa bb', 5) == ['aa bb']
def test_no_fit(): assert f('aa bb', 4) == ['aa', 'bb']
def test_long_word(): assert f('abcdefgh xy', 3) == ['abc', 'def', 'gh', 'xy']
def test_remainder_joins(): assert f('abcd x', 3) == ['abc', 'd x']
def test_whitespace_only(): assert f(' \t ', 5) == []
def test_single_word(): assert f('hi', 10) == ['hi']
def test_bad_width_zero():
    with pytest.raises(ValueError) as e: f('a', 0)
    assert str(e.value) == 'bad width'
def test_bad_width_bool():
    with pytest.raises(ValueError): f('a', True)
''',
        "hard", max_new_tokens=768),
    TaskSpec(
        "identifier_words",
        "Write a Python function split_identifier(s) that splits a programming "
        "identifier into its constituent words and returns them as a list of "
        "strings preserving original case. Allowed characters are ASCII "
        "letters, ASCII digits, and underscores; any other character (including "
        "non-ASCII letters) -> ValueError('bad char'). Underscores are pure "
        "separators: they are removed, runs of underscores act as one "
        "separator, and leading or trailing underscores produce no words. "
        "Within a run of letters and digits, words break at every letter-digit "
        "or digit-letter boundary and at every lowercase-to-uppercase boundary. "
        "A run of two or more consecutive uppercase letters is an acronym: if "
        "it is immediately followed by a lowercase letter, the LAST uppercase "
        "letter belongs to the following word (so an acronym then a "
        "capitalized word split before that final capital). A single uppercase "
        "letter followed by lowercase letters forms one capitalized word. "
        "Digit runs are whole words. An empty input (or one that is only "
        "underscores) returns []. Output ONLY the function definition.",
        "solution.py",
        r'''def split_identifier(s):
    for ch in s:
        if not (ch.isascii() and (ch.isalnum() or ch == "_")):
            raise ValueError("bad char")
    out = []
    for part in s.split("_"):
        i, n = 0, len(part)
        while i < n:
            c = part[i]
            j = i + 1
            if c.isdigit():
                while j < n and part[j].isdigit():
                    j += 1
            elif c.isupper():
                while j < n and part[j].isupper():
                    j += 1
                if j - i == 1:
                    while j < n and part[j].islower():
                        j += 1
                elif j < n and part[j].islower():
                    j -= 1
            else:
                while j < n and part[j].islower():
                    j += 1
            out.append(part[i:j])
            i = j
    return out
''',
        r'''import pytest
from solution import split_identifier as f
def test_acronym_then_word(): assert f('HTTPServer2Node') == ['HTTP', 'Server', '2', 'Node']
def test_camel_acronym(): assert f('parseJSON2XML') == ['parse', 'JSON', '2', 'XML']
def test_snake(): assert f('snake_case_two') == ['snake', 'case', 'two']
def test_underscore_trim(): assert f('__x__') == ['x']
def test_empty(): assert f('') == []
def test_two_caps_then_lower(): assert f('ABc') == ['A', 'Bc']
def test_plain(): assert f('simple') == ['simple']
def test_single_cap_then_digit(): assert f('A1a') == ['A', '1', 'a']
def test_bad_char():
    with pytest.raises(ValueError) as e: f('a-b')
    assert str(e.value) == 'bad char'
''',
        "hard", max_new_tokens=768),
    TaskSpec(
        "tab_expand_columns",
        "Write a Python function expand_tabs(s, stop) that expands tab "
        "characters into spaces using tab stops every `stop` columns and "
        "returns the resulting string. stop must be an int, must not be a "
        "bool, and must be at least 1; otherwise -> ValueError('bad stop'). "
        "Column arithmetic: the column starts at 0; every character other "
        "than tab and newline advances the column by exactly 1 and is copied "
        "through unchanged. A tab is replaced by however many spaces are "
        "needed to reach the NEXT multiple of stop; a tab sitting exactly on a "
        "multiple of stop still advances a full stop (it never produces zero "
        "spaces). A newline is copied through and resets the column to 0. "
        "Carriage returns and all other control characters are ordinary "
        "one-column characters. The empty string returns ''. Output ONLY the "
        "function definition.",
        "solution.py",
        r'''def expand_tabs(s, stop):
    if not isinstance(stop, int) or isinstance(stop, bool) or stop < 1:
        raise ValueError("bad stop")
    out = []
    col = 0
    for c in s:
        if c == "\t":
            pad = stop - (col % stop)
            out.append(" " * pad)
            col += pad
        elif c == "\n":
            out.append(c)
            col = 0
        else:
            out.append(c)
            col += 1
    return "".join(out)
''',
        r'''import pytest
from solution import expand_tabs as f
def test_basic(): assert f('a\tb', 4) == 'a   b'
def test_tab_on_stop(): assert f('abcd\tb', 4) == 'abcd    b'
def test_two_tabs(): assert f('ab\tc\td', 4) == 'ab  c   d'
def test_newline_resets(): assert f('a\nb\tc', 4) == 'a\nb   c'
def test_empty(): assert f('', 4) == ''
def test_stop_one(): assert f('\t', 1) == ' '
def test_bad_stop_zero():
    with pytest.raises(ValueError) as e: f('a', 0)
    assert str(e.value) == 'bad stop'
def test_bad_stop_bool():
    with pytest.raises(ValueError): f('a', True)
''',
        "hard", max_new_tokens=768),
    TaskSpec(
        "interval_subtract",
        "Write a Python function interval_subtract(a, b) computing the "
        "difference of two closed INTEGER interval lists. Each list contains "
        "[start, end] pairs of ints; both lists are already sorted by start "
        "and internally disjoint. Before any computation, every interval in "
        "BOTH lists must satisfy start <= end; any violation -> "
        "ValueError('bad interval'). Semantics are integer semantics on "
        "closed intervals: the result covers exactly the integers covered by "
        "some interval of a but by no interval of b, expressed as the sorted "
        "list of maximal closed intervals [start, end] (a single surviving "
        "integer x appears as [x, x]). For example removing [3,5] from [1,10] "
        "leaves [1,2] and [6,10]. One b interval may bite several a intervals "
        "and vice versa. Touching matters: removing [5,9] from [1,5] leaves "
        "[1,4]. Empty a returns []; empty b returns the intervals of a "
        "unchanged in value. Output ONLY the function definition.",
        "solution.py",
        r'''def interval_subtract(a, b):
    for lst in (a, b):
        for iv in lst:
            if iv[0] > iv[1]:
                raise ValueError("bad interval")
    out = []
    j = 0
    for lo, hi in a:
        cur = lo
        while j < len(b) and b[j][1] < cur:
            j += 1
        k = j
        while k < len(b) and b[k][0] <= hi:
            blo, bhi = b[k]
            if blo > cur:
                out.append([cur, blo - 1])
            cur = max(cur, bhi + 1)
            k += 1
        if cur <= hi:
            out.append([cur, hi])
    return out
''',
        r'''import pytest
from solution import interval_subtract as f
def test_middle_bite(): assert f([[1, 10]], [[3, 5]]) == [[1, 2], [6, 10]]
def test_one_b_two_a(): assert f([[1, 3], [6, 9]], [[2, 7]]) == [[1, 1], [8, 9]]
def test_exact_removal(): assert f([[1, 5]], [[1, 5]]) == []
def test_empty_b(): assert f([[1, 5]], []) == [[1, 5]]
def test_empty_a(): assert f([], [[1, 2]]) == []
def test_touching(): assert f([[1, 5]], [[5, 9]]) == [[1, 4]]
def test_b_between(): assert f([[0, 3], [5, 8]], [[4, 4]]) == [[0, 3], [5, 8]]
def test_b_spans_all(): assert f([[1, 2], [4, 5]], [[0, 10]]) == []
def test_bad_interval():
    with pytest.raises(ValueError) as e: f([[5, 1]], [])
    assert str(e.value) == 'bad interval'
''',
        "hard", max_new_tokens=768),
    TaskSpec(
        "rect_overlap_area",
        "Write a Python function rect_overlap(r1, r2) returning the area of "
        "the intersection of two axis-aligned rectangles as an int. Each "
        "rectangle must be EXACTLY a tuple of exactly 4 values (x1, y1, x2, "
        "y2); each value must be an int and must not be a bool; and it must "
        "satisfy x1 <= x2 and y1 <= y2. Any violation of any of these -> "
        "ValueError('bad rect'). (x1, y1) is one corner and (x2, y2) the "
        "opposite corner; coordinates may be negative. Degenerate rectangles "
        "with zero width or height are VALID inputs and simply have zero "
        "area. Rectangles that only touch along an edge or at a corner "
        "overlap with area 0, not an error. Return the exact integer overlap "
        "area, 0 whenever the interiors do not intersect. Output ONLY the "
        "function definition.",
        "solution.py",
        r'''def rect_overlap(r1, r2):
    for r in (r1, r2):
        if type(r) is not tuple or len(r) != 4:
            raise ValueError("bad rect")
        for v in r:
            if not isinstance(v, int) or isinstance(v, bool):
                raise ValueError("bad rect")
        if r[0] > r[2] or r[1] > r[3]:
            raise ValueError("bad rect")
    w = min(r1[2], r2[2]) - max(r1[0], r2[0])
    h = min(r1[3], r2[3]) - max(r1[1], r2[1])
    if w <= 0 or h <= 0:
        return 0
    return w * h
''',
        r'''import pytest
from solution import rect_overlap as f
def test_overlap(): assert f((0, 0, 4, 4), (2, 2, 6, 6)) == 4
def test_nested(): assert f((0, 0, 10, 10), (2, 3, 4, 5)) == 4
def test_touching_edge(): assert f((0, 0, 2, 2), (2, 0, 4, 2)) == 0
def test_disjoint(): assert f((0, 0, 1, 1), (5, 5, 6, 6)) == 0
def test_degenerate(): assert f((0, 0, 0, 5), (0, 0, 5, 5)) == 0
def test_negative_coords(): assert f((-3, -3, 1, 1), (-1, -1, 0, 0)) == 1
def test_list_rejected():
    with pytest.raises(ValueError) as e: f([0, 0, 1, 1], (0, 0, 1, 1))
    assert str(e.value) == 'bad rect'
def test_inverted():
    with pytest.raises(ValueError): f((1, 0, 0, 1), (0, 0, 1, 1))
def test_bool_coord():
    with pytest.raises(ValueError): f((0, 0, True, 1), (0, 0, 1, 1))
''',
        "hard", max_new_tokens=768),
    TaskSpec(
        "covered_integer_count",
        "Write a Python function count_covered(intervals) returning how many "
        "distinct INTEGERS are covered by a list of closed integer intervals. "
        "intervals is a list of [start, end] pairs in ARBITRARY order that "
        "may overlap, nest, duplicate, or touch. Every bound must be an int "
        "and must not be a bool, and every interval must satisfy start <= "
        "end; any violation -> ValueError('bad interval'). Counting is over "
        "integers, not length: [1, 3] covers the three integers 1, 2, 3, and "
        "the adjacent pair [1, 2] plus [3, 4] covers four integers in total. "
        "Overlapping regions count once ([1, 3] with [2, 5] covers five). "
        "The input list must NOT be mutated: do not sort it in place and do "
        "not reorder its elements. Bounds may be negative. An empty list "
        "returns 0. Output ONLY the function definition.",
        "solution.py",
        r'''def count_covered(intervals):
    ivs = []
    for iv in intervals:
        lo, hi = iv[0], iv[1]
        for v in (lo, hi):
            if not isinstance(v, int) or isinstance(v, bool):
                raise ValueError("bad interval")
        if lo > hi:
            raise ValueError("bad interval")
        ivs.append((lo, hi))
    ivs.sort()
    total = 0
    cur_lo = cur_hi = None
    for lo, hi in ivs:
        if cur_lo is None:
            cur_lo, cur_hi = lo, hi
        elif lo <= cur_hi + 1:
            cur_hi = max(cur_hi, hi)
        else:
            total += cur_hi - cur_lo + 1
            cur_lo, cur_hi = lo, hi
    if cur_lo is not None:
        total += cur_hi - cur_lo + 1
    return total
''',
        r'''import pytest
from solution import count_covered as f
def test_overlap(): assert f([[1, 3], [2, 5]]) == 5
def test_adjacent(): assert f([[1, 2], [3, 4]]) == 4
def test_empty(): assert f([]) == 0
def test_duplicates(): assert f([[1, 1], [1, 1]]) == 1
def test_negative(): assert f([[-5, -3], [10, 10]]) == 4
def test_no_mutation():
    g = [[5, 7], [1, 2]]
    assert f(g) == 5
    assert g == [[5, 7], [1, 2]]
def test_inverted():
    with pytest.raises(ValueError) as e: f([[3, 1]])
    assert str(e.value) == 'bad interval'
def test_bool_bound():
    with pytest.raises(ValueError): f([[True, 2]])
''',
        "hard", max_new_tokens=768),
    TaskSpec(
        "turtle_walk_program",
        "Write a Python function turtle(prog) that runs a turtle-graphics "
        "command string and returns the final state as a tuple (x, y, "
        "heading). The turtle starts at (0, 0) heading 'N'; headings are the "
        "letters N, E, S, W with x growing east and y growing north. Commands "
        "are single characters: 'F' moves one step in the current heading, "
        "'B' moves one step backward WITHOUT changing heading, 'L' and 'R' "
        "rotate 90 degrees left/right. A command may be prefixed by a "
        "repetition count: one or more ASCII digits meaning the command "
        "repeats that many times ('12F' moves forward twelve). A count whose "
        "first digit is '0' -> ValueError('bad count'). A run of digits at "
        "the very end of the program with no command after it -> "
        "ValueError('dangling count'). Any character that is not a digit and "
        "not one of F, B, L, R -> ValueError('bad command'). Errors are "
        "detected left to right as the program is scanned. The empty program "
        "returns (0, 0, 'N'). Output ONLY the function definition.",
        "solution.py",
        r'''def turtle(prog):
    dirs = "NESW"
    dx = {"N": 0, "E": 1, "S": 0, "W": -1}
    dy = {"N": 1, "E": 0, "S": -1, "W": 0}
    x = y = h = 0
    i = 0
    n = len(prog)
    while i < n:
        c = prog[i]
        count = 1
        if c.isdigit():
            j = i
            while j < n and prog[j].isdigit():
                j += 1
            if prog[i] == "0":
                raise ValueError("bad count")
            if j >= n:
                raise ValueError("dangling count")
            count = int(prog[i:j])
            i = j
            c = prog[i]
        if c == "L":
            h = (h - count) % 4
        elif c == "R":
            h = (h + count) % 4
        elif c == "F":
            d = dirs[h]
            x += dx[d] * count
            y += dy[d] * count
        elif c == "B":
            d = dirs[h]
            x -= dx[d] * count
            y -= dy[d] * count
        else:
            raise ValueError("bad command")
        i += 1
    return (x, y, dirs[h])
''',
        r'''import pytest
from solution import turtle as f
def test_empty(): assert f('') == (0, 0, 'N')
def test_walk(): assert f('2FR3F') == (3, 2, 'E')
def test_backward(): assert f('B') == (0, -1, 'N')
def test_double_left(): assert f('2L') == (0, 0, 'S')
def test_multidigit(): assert f('10F') == (0, 10, 'N')
def test_full_circle(): assert f('LLLL') == (0, 0, 'N')
def test_zero_count():
    with pytest.raises(ValueError) as e: f('0F')
    assert str(e.value) == 'bad count'
def test_leading_zero_count():
    with pytest.raises(ValueError) as e: f('07F')
    assert str(e.value) == 'bad count'
def test_dangling():
    with pytest.raises(ValueError) as e: f('F12')
    assert str(e.value) == 'dangling count'
def test_unknown():
    with pytest.raises(ValueError) as e: f('FxF')
    assert str(e.value) == 'bad command'
''',
        "hard", max_new_tokens=768),
    TaskSpec(
        "token_bucket_grants",
        "Write a Python function grant_requests(capacity, events) simulating "
        "a token-bucket rate limiter and returning a list of bools, one per "
        "event, True when the request was granted. capacity must be an int, "
        "not a bool, and at least 1 -> otherwise ValueError('bad capacity'). "
        "events is a list; each event must be EXACTLY a tuple of exactly two "
        "values (timestamp, amount), both ints and neither a bool, with "
        "amount at least 1; any violation -> ValueError('bad event'). "
        "Timestamps must be non-decreasing across the list; a timestamp "
        "smaller than its predecessor -> ValueError('time warp'). Events are "
        "validated and processed strictly in list order, so a malformed "
        "event is only reported when reached. Bucket semantics: the bucket "
        "holds `capacity` tokens and is FULL before the first event. Between "
        "consecutive events it refills by 1 token per unit of elapsed "
        "timestamp difference, capped at capacity; the refill is applied "
        "before judging the request at that timestamp, and two events with "
        "equal timestamps get no refill between them. A request is granted "
        "iff the bucket then holds at least `amount` tokens, and a granted "
        "request removes `amount` tokens; a denied request removes nothing. "
        "An amount larger than capacity is a legal request that is simply "
        "always denied. An empty events list returns []. Output ONLY the "
        "function definition.",
        "solution.py",
        r'''def grant_requests(capacity, events):
    if not isinstance(capacity, int) or isinstance(capacity, bool) or capacity < 1:
        raise ValueError("bad capacity")
    tokens = capacity
    last = None
    out = []
    for ev in events:
        if type(ev) is not tuple or len(ev) != 2:
            raise ValueError("bad event")
        ts, amt = ev
        for v in (ts, amt):
            if not isinstance(v, int) or isinstance(v, bool):
                raise ValueError("bad event")
        if amt < 1:
            raise ValueError("bad event")
        if last is not None and ts < last:
            raise ValueError("time warp")
        if last is not None:
            tokens = min(capacity, tokens + (ts - last))
        last = ts
        if tokens >= amt:
            tokens -= amt
            out.append(True)
        else:
            out.append(False)
    return out
''',
        r'''import pytest
from solution import grant_requests as f
def test_same_ts_no_refill(): assert f(5, [(0, 3), (0, 3)]) == [True, False]
def test_refill(): assert f(5, [(0, 3), (2, 3)]) == [True, True]
def test_over_capacity(): assert f(3, [(0, 4)]) == [False]
def test_partial_refill(): assert f(5, [(0, 5), (1, 5)]) == [True, False]
def test_refill_cap(): assert f(5, [(0, 1), (100, 5)]) == [True, True]
def test_empty(): assert f(5, []) == []
def test_time_warp():
    with pytest.raises(ValueError) as e: f(5, [(1, 1), (0, 1)])
    assert str(e.value) == 'time warp'
def test_bad_capacity():
    with pytest.raises(ValueError) as e: f(0, [])
    assert str(e.value) == 'bad capacity'
def test_zero_amount():
    with pytest.raises(ValueError) as e: f(5, [(0, 0)])
    assert str(e.value) == 'bad event'
def test_list_event():
    with pytest.raises(ValueError): f(5, [[0, 1]])
''',
        "hard", max_new_tokens=768),
    TaskSpec(
        "stopwatch_fsm",
        "Write a Python function stopwatch(events) simulating a stopwatch "
        "and returning a tuple (total, laps). events is a list of (timestamp, "
        "op) items processed in order. Each item must be EXACTLY a tuple of "
        "exactly two values, the timestamp an int and not a bool, and the op "
        "one of the strings 'start', 'stop', 'lap', 'reset'; any violation "
        "-> ValueError('bad event'). Timestamps must be STRICTLY increasing "
        "across the whole list; an equal or smaller timestamp -> "
        "ValueError('time warp'). The stopwatch begins stopped with an "
        "accumulated total of 0 and no laps. 'start' while already running "
        "-> ValueError('already running'); otherwise it marks the segment "
        "start. 'stop' while not running -> ValueError('not running'); "
        "otherwise it adds the elapsed segment time to the accumulated "
        "total. 'lap' while not running -> ValueError('not running'); while "
        "running it records the CURRENT total elapsed time (accumulated "
        "completed segments plus the running segment so far) into the laps "
        "list. 'reset' while running -> ValueError('still running'); while "
        "stopped it zeroes the accumulated total AND clears the laps list. "
        "Return (total, laps) where total counts only COMPLETED segments: a "
        "segment still running when the list ends contributes nothing. An "
        "empty list returns (0, []). Output ONLY the function definition.",
        "solution.py",
        r'''def stopwatch(events):
    ops = ("start", "stop", "lap", "reset")
    total = 0
    laps = []
    running = False
    started = 0
    last = None
    for ev in events:
        if type(ev) is not tuple or len(ev) != 2:
            raise ValueError("bad event")
        ts, op = ev
        if not isinstance(ts, int) or isinstance(ts, bool) or op not in ops:
            raise ValueError("bad event")
        if last is not None and ts <= last:
            raise ValueError("time warp")
        last = ts
        if op == "start":
            if running:
                raise ValueError("already running")
            running = True
            started = ts
        elif op == "stop":
            if not running:
                raise ValueError("not running")
            total += ts - started
            running = False
        elif op == "lap":
            if not running:
                raise ValueError("not running")
            laps.append(total + (ts - started))
        else:
            if running:
                raise ValueError("still running")
            total = 0
            laps = []
    return (total, laps)
''',
        r'''import pytest
from solution import stopwatch as f
def test_empty(): assert f([]) == (0, [])
def test_one_segment(): assert f([(0, 'start'), (5, 'stop')]) == (5, [])
def test_laps(): assert f([(0, 'start'), (3, 'lap'), (5, 'stop'), (7, 'start'), (9, 'lap'), (10, 'stop')]) == (8, [3, 7])
def test_reset(): assert f([(0, 'start'), (5, 'stop'), (6, 'reset'), (7, 'start'), (9, 'stop')]) == (2, [])
def test_running_at_end(): assert f([(0, 'start')]) == (0, [])
def test_double_start():
    with pytest.raises(ValueError) as e: f([(0, 'start'), (1, 'start')])
    assert str(e.value) == 'already running'
def test_stop_stopped():
    with pytest.raises(ValueError) as e: f([(0, 'stop')])
    assert str(e.value) == 'not running'
def test_lap_stopped():
    with pytest.raises(ValueError) as e: f([(0, 'lap')])
    assert str(e.value) == 'not running'
def test_reset_running():
    with pytest.raises(ValueError) as e: f([(0, 'start'), (1, 'reset')])
    assert str(e.value) == 'still running'
def test_time_warp():
    with pytest.raises(ValueError) as e: f([(0, 'start'), (0, 'stop')])
    assert str(e.value) == 'time warp'
def test_bad_op():
    with pytest.raises(ValueError) as e: f([(0, 'go')])
    assert str(e.value) == 'bad event'
''',
        "hard", max_new_tokens=768),
    TaskSpec(
        "matrix_shape_strict",
        "Write a Python function matrix_shape(m) that validates a rectangular "
        "numeric matrix and returns its shape as a tuple (rows, columns). "
        "Checks run in a fixed order and only the FIRST failure is reported, "
        "each as a ValueError with exactly the given message. First: m must "
        "be a list -> 'not a list'; then m must be non-empty -> 'empty'. "
        "Then rows are examined strictly top to bottom, and for each row in "
        "this order: the row must be a list -> 'row not list'; the row must "
        "be non-empty -> 'empty row'; the row's length must equal the first "
        "row's length -> 'ragged'; then the row's cells are scanned left to "
        "right and each must be an int or a float but never a bool -> 'bad "
        "cell'. Note the ordering consequences: a bad cell in row 1 is "
        "reported even when row 2 is ragged, but a row's own length check "
        "fires before that same row's cells are scanned. Return (number of "
        "rows, number of columns) after all checks pass. Output ONLY the "
        "function definition.",
        "solution.py",
        r'''def matrix_shape(m):
    if not isinstance(m, list):
        raise ValueError("not a list")
    if not m:
        raise ValueError("empty")
    width = None
    for row in m:
        if not isinstance(row, list):
            raise ValueError("row not list")
        if not row:
            raise ValueError("empty row")
        if width is None:
            width = len(row)
        elif len(row) != width:
            raise ValueError("ragged")
        for cell in row:
            if isinstance(cell, bool) or not isinstance(cell, (int, float)):
                raise ValueError("bad cell")
    return (len(m), width)
''',
        r'''import pytest
from solution import matrix_shape as f
def test_shape(): assert f([[1, 2, 3], [4, 5, 6]]) == (2, 3)
def test_float_cell(): assert f([[1.5]]) == (1, 1)
def test_not_list():
    with pytest.raises(ValueError) as e: f(5)
    assert str(e.value) == 'not a list'
def test_empty():
    with pytest.raises(ValueError) as e: f([])
    assert str(e.value) == 'empty'
def test_row_not_list():
    with pytest.raises(ValueError) as e: f([[1], (2,)])
    assert str(e.value) == 'row not list'
def test_empty_row():
    with pytest.raises(ValueError) as e: f([[1], []])
    assert str(e.value) == 'empty row'
def test_ragged():
    with pytest.raises(ValueError) as e: f([[1, 2], [3]])
    assert str(e.value) == 'ragged'
def test_bad_cell():
    with pytest.raises(ValueError) as e: f([[1, True]])
    assert str(e.value) == 'bad cell'
def test_cell_before_later_ragged():
    with pytest.raises(ValueError) as e: f([[1, 'x'], [2]])
    assert str(e.value) == 'bad cell'
def test_ragged_before_own_cells():
    with pytest.raises(ValueError) as e: f([[1, 2], [3, 'x', 4]])
    assert str(e.value) == 'ragged'
''',
        "hard", max_new_tokens=768),
    TaskSpec(
        "money_cents_strict",
        "Write a Python function parse_money(s) that parses a strictly "
        "formatted decimal money amount and returns the value as an integer "
        "number of cents. Grammar: an optional single leading '-' (no '+'), "
        "then the integer part, then optionally a '.' followed by EXACTLY two "
        "digits. The integer part is either plain digits with no separators "
        "and no leading zero (except exactly '0' by itself), or comma-grouped: "
        "a first group of 1 to 3 digits not starting with '0', followed by "
        "one or more groups of exactly 3 digits each preceded by a comma. "
        "Mixing is not allowed: once commas appear, every group after the "
        "first must be exactly 3 digits. Anything violating the grammar -> "
        "ValueError('bad amount'): that includes '.50' (missing integer "
        "part), '1.5' (one decimal digit), '1.505' (three), '007', '0,123', "
        "'12,34', '1,2345', '+1', whitespace anywhere, and the empty string. "
        "A minus sign with a zero value is legal input and the function then "
        "returns 0 (so '-0.00' gives 0). Examples: '1,234.56' gives 123456; "
        "'-12' gives -1200; '0.99' gives 99. Output ONLY the function "
        "definition.",
        "solution.py",
        r'''def parse_money(s):
    import re
    m = re.fullmatch(r"(-?)(0|[1-9]\d*|[1-9]\d{0,2}(?:,\d{3})+)(?:\.(\d{2}))?", s)
    if not m:
        raise ValueError("bad amount")
    sign, whole, frac = m.group(1), m.group(2), m.group(3)
    cents = int(whole.replace(",", "")) * 100 + (int(frac) if frac else 0)
    return -cents if sign else cents
''',
        r'''import pytest
from solution import parse_money as f
def test_grouped(): assert f('1,234.56') == 123456
def test_cents_only(): assert f('0.99') == 99
def test_negative(): assert f('-12') == -1200
def test_million(): assert f('1,000,000') == 100000000
def test_negative_zero(): assert f('-0.00') == 0
def test_zero(): assert f('0') == 0
def test_leading_zeros():
    with pytest.raises(ValueError) as e: f('007')
    assert str(e.value) == 'bad amount'
def test_bad_group():
    with pytest.raises(ValueError): f('1,23.45')
def test_no_integer_part():
    with pytest.raises(ValueError): f('.50')
def test_one_decimal():
    with pytest.raises(ValueError): f('1.5')
def test_plus():
    with pytest.raises(ValueError): f('+1')
def test_zero_grouped():
    with pytest.raises(ValueError): f('0,123')
''',
        "hard", max_new_tokens=768),
    TaskSpec(
        "cron_field_expand",
        "Write a Python function cron_field(field, lo, hi) that expands one "
        "cron-style field string into the sorted deduplicated list of "
        "matching integers within the inclusive bounds [lo, hi]. lo and hi "
        "must both be ints and not bools with lo <= hi; otherwise -> "
        "ValueError('bad bounds'). The field is a comma-separated list of "
        "items with no whitespace anywhere. Each item is one of: '*' (every "
        "value from lo to hi); '*/K' (lo, lo+K, lo+2K, ... up to hi); 'N' (a "
        "single value); 'N-M' (every value from N to M inclusive); or "
        "'N-M/K' (N, N+K, ... up to M). N, M, K are unsigned decimal digit "
        "runs; leading zeros are ALLOWED and carry no meaning. A step on a "
        "bare single value (an item shaped like 'N/K') is invalid syntax. "
        "Error taxonomy, each a ValueError with exactly the message: any "
        "syntactically malformed item (empty item, empty field, missing "
        "digits, signs, stray characters, a step attached to a bare value) "
        "-> 'bad field'; a range with N greater than M -> 'bad range'; an N "
        "or M outside [lo, hi] -> 'out of range'; a step K equal to 0 -> "
        "'bad step'. Duplicates across items are fine and collapse in the "
        "sorted output. Output ONLY the function definition.",
        "solution.py",
        r'''def cron_field(field, lo, hi):
    for v in (lo, hi):
        if not isinstance(v, int) or isinstance(v, bool):
            raise ValueError("bad bounds")
    if lo > hi:
        raise ValueError("bad bounds")
    vals = set()
    for item in field.split(","):
        step = 1
        body = item
        if "/" in item:
            body, _, stext = item.partition("/")
            if not stext.isdigit():
                raise ValueError("bad field")
            step = int(stext)
            if step == 0:
                raise ValueError("bad step")
        if body == "*":
            start, end = lo, hi
        elif "-" in body:
            a, _, b = body.partition("-")
            if not a.isdigit() or not b.isdigit():
                raise ValueError("bad field")
            start, end = int(a), int(b)
            if start > end:
                raise ValueError("bad range")
            if start < lo or end > hi:
                raise ValueError("out of range")
        else:
            if "/" in item:
                raise ValueError("bad field")
            if not body.isdigit():
                raise ValueError("bad field")
            start = end = int(body)
            if start < lo or start > hi:
                raise ValueError("out of range")
        vals.update(range(start, end + 1, step))
    return sorted(vals)
''',
        r'''import pytest
from solution import cron_field as f
def test_star(): assert f('*', 0, 5) == [0, 1, 2, 3, 4, 5]
def test_star_step(): assert f('*/15', 0, 59) == [0, 15, 30, 45]
def test_range_step(): assert f('3-7/2', 0, 59) == [3, 5, 7]
def test_list_dedup(): assert f('1,5,3,5', 0, 59) == [1, 3, 5]
def test_mixed(): assert f('10-12,1', 0, 59) == [1, 10, 11, 12]
def test_leading_zero_value(): assert f('05', 0, 59) == [5]
def test_step_on_value():
    with pytest.raises(ValueError) as e: f('5/2', 0, 59)
    assert str(e.value) == 'bad field'
def test_reversed_range():
    with pytest.raises(ValueError) as e: f('7-3', 0, 59)
    assert str(e.value) == 'bad range'
def test_out_of_range():
    with pytest.raises(ValueError) as e: f('0-99', 0, 59)
    assert str(e.value) == 'out of range'
def test_zero_step():
    with pytest.raises(ValueError) as e: f('*/0', 0, 59)
    assert str(e.value) == 'bad step'
def test_bad_bounds():
    with pytest.raises(ValueError) as e: f('*', 5, 0)
    assert str(e.value) == 'bad bounds'
def test_empty_field():
    with pytest.raises(ValueError) as e: f('', 0, 5)
    assert str(e.value) == 'bad field'
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
