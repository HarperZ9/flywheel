#!/usr/bin/env python3
"""seed_hard_v2_b6.py - batch 6 for the N>=100 hard-set lane (target ~70/100).

Same contract as batches 1-5: soundness admission through task_curator gates;
difficulty screening against the served 14B is a later arm. Batch 6 doctrine:
contract density over textbook fame. Difficulty comes from precise multi-clause
prose contracts (error taxonomies, canonical ordering, exact exception types,
rounding/overflow semantics, escaping edge cases) not famous algorithms. Domains
in this file are ones the first 50 barely touch: arbitrary-base number
conversion, spreadsheet-column bijection, checksum validators (Luhn, ISBN-10),
Gregorian calendar arithmetic, semantic-version and natural-order comparison,
percent/CSV escaping, exact half-even rounding, bit reversal, fraction reduction.
Each task is a single top-level function; the prompt states the full contract in
prose with no solution code; the hidden tests assert exact semantics on
adversarial edges. The remaining authoring wave (streaming aggregation, small
parsers and evaluators, list/grid transforms) lives in seed_hard_v2_b7.py.
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
        "int_to_base",
        "Write a Python function to_base(n, base) that renders an integer in an "
        "arbitrary base and returns the string. base must be an int, must not be "
        "a bool, and must satisfy 2 <= base <= 36; otherwise -> "
        "ValueError('bad base'). n must be an int and must not be a bool; "
        "otherwise -> ValueError('bad number'). Digits above 9 use the lowercase "
        "letters a through z, so base 16 uses 0-9 then a-f. The value zero always "
        "renders as the single character 0. A negative number renders as a single "
        "leading minus sign followed by the rendering of its absolute value. The "
        "result never carries redundant leading zeros (other than the lone 0 for "
        "zero itself) and never carries a plus sign. Output ONLY the function "
        "definition.",
        "solution.py",
        r'''def to_base(n, base):
    if not isinstance(base, int) or isinstance(base, bool) or base < 2 or base > 36:
        raise ValueError("bad base")
    if not isinstance(n, int) or isinstance(n, bool):
        raise ValueError("bad number")
    if n == 0:
        return "0"
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    neg = n < 0
    n = abs(n)
    out = []
    while n:
        out.append(digits[n % base])
        n //= base
    if neg:
        out.append("-")
    return "".join(reversed(out))
''',
        r'''import pytest
from solution import to_base as f
def test_hex(): assert f(255, 16) == 'ff'
def test_zero(): assert f(0, 2) == '0'
def test_binary(): assert f(10, 2) == '1010'
def test_negative(): assert f(-31, 16) == '-1f'
def test_top_digit(): assert f(35, 36) == 'z'
def test_rollover(): assert f(36, 36) == '10'
def test_bad_base_low():
    with pytest.raises(ValueError) as e: f(5, 1)
    assert str(e.value) == 'bad base'
def test_bad_base_high():
    with pytest.raises(ValueError): f(5, 37)
def test_bad_base_bool():
    with pytest.raises(ValueError) as e: f(5, True)
    assert str(e.value) == 'bad base'
def test_bad_number_bool():
    with pytest.raises(ValueError) as e: f(True, 2)
    assert str(e.value) == 'bad number'
''',
        "hard", max_new_tokens=768),
    TaskSpec(
        "parse_base",
        "Write a Python function from_base(s, base) that parses a string of "
        "digits in an arbitrary base and returns the integer value. base must be "
        "an int, must not be a bool, and must satisfy 2 <= base <= 36; otherwise "
        "-> ValueError('bad base'). s must be a str. Parsing is case insensitive: "
        "digits above 9 are the letters a through z (or A through Z) with a "
        "meaning 10 up to z meaning 35. An optional single leading minus sign is "
        "allowed and negates the value; no plus sign is allowed. Leading zeros are "
        "permitted and carry no meaning. Any of the following -> "
        "ValueError('bad digits'): an empty string, a string that is only the "
        "minus sign, a character that is not a valid digit for the given base, "
        "a digit whose value is not strictly less than base, and any whitespace. "
        "Output ONLY the function definition.",
        "solution.py",
        r'''def from_base(s, base):
    if not isinstance(base, int) or isinstance(base, bool) or base < 2 or base > 36:
        raise ValueError("bad base")
    if not isinstance(s, str) or s == "":
        raise ValueError("bad digits")
    body = s
    neg = False
    if body[0] == "-":
        neg = True
        body = body[1:]
    if body == "":
        raise ValueError("bad digits")
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    val = 0
    for ch in body.lower():
        d = digits.find(ch)
        if d < 0 or d >= base:
            raise ValueError("bad digits")
        val = val * base + d
    return -val if neg else val
''',
        r'''import pytest
from solution import from_base as f
def test_hex(): assert f('ff', 16) == 255
def test_upper(): assert f('FF', 16) == 255
def test_binary(): assert f('1010', 2) == 10
def test_negative(): assert f('-1f', 16) == -31
def test_leading_zeros(): assert f('007', 10) == 7
def test_top_digit(): assert f('z', 36) == 35
def test_digit_ge_base():
    with pytest.raises(ValueError) as e: f('12', 2)
    assert str(e.value) == 'bad digits'
def test_empty():
    with pytest.raises(ValueError) as e: f('', 10)
    assert str(e.value) == 'bad digits'
def test_lone_minus():
    with pytest.raises(ValueError): f('-', 10)
def test_plus():
    with pytest.raises(ValueError): f('+5', 10)
def test_bad_base():
    with pytest.raises(ValueError) as e: f('1', 1)
    assert str(e.value) == 'bad base'
''',
        "hard", max_new_tokens=768),
    TaskSpec(
        "roman_encode",
        "Write a Python function to_roman(n) that renders a positive integer as "
        "an uppercase Roman numeral string in strict subtractive form. n must be "
        "an int, must not be a bool, and must satisfy 1 <= n <= 3999; otherwise "
        "-> ValueError('out of range'). Use the standard symbols where I is 1, V "
        "is 5, X is 10, L is 50, C is 100, D is 500, M is 1000, and the six "
        "subtractive compounds IV is 4, IX is 9, XL is 40, XC is 90, CD is 400, "
        "CM is 900. Greedily emit the largest value that fits, so 1994 renders as "
        "MCMXCIV and 58 as LVIII. A symbol is never repeated four times in a row "
        "because the subtractive compounds are used instead. Output ONLY the "
        "function definition.",
        "solution.py",
        r'''def to_roman(n):
    if not isinstance(n, int) or isinstance(n, bool) or n < 1 or n > 3999:
        raise ValueError("out of range")
    table = [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
             (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
             (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]
    out = []
    for value, sym in table:
        while n >= value:
            out.append(sym)
            n -= value
    return "".join(out)
''',
        r'''import pytest
from solution import to_roman as f
def test_four(): assert f(4) == 'IV'
def test_nine(): assert f(9) == 'IX'
def test_fifty_eight(): assert f(58) == 'LVIII'
def test_big(): assert f(1994) == 'MCMXCIV'
def test_max(): assert f(3999) == 'MMMCMXCIX'
def test_one(): assert f(1) == 'I'
def test_forty(): assert f(40) == 'XL'
def test_below():
    with pytest.raises(ValueError) as e: f(0)
    assert str(e.value) == 'out of range'
def test_above():
    with pytest.raises(ValueError): f(4000)
def test_bool():
    with pytest.raises(ValueError): f(True)
''',
        "hard", max_new_tokens=768),
    TaskSpec(
        "col_label",
        "Write a Python function col_label(n) that converts a positive column "
        "index into its spreadsheet column label and returns the string. The "
        "mapping is a bijective base-26 numbering: 1 is A, 26 is Z, 27 is AA, 28 "
        "is AB, 52 is AZ, 53 is BA, 702 is ZZ, 703 is AAA. There is no zero digit "
        "and no leading-A padding because the scheme is bijective, not ordinary "
        "positional base 26. n must be an int, must not be a bool, and must be at "
        "least 1; otherwise -> ValueError('bad column'). The label is always "
        "uppercase ASCII letters. Output ONLY the function definition.",
        "solution.py",
        r'''def col_label(n):
    if not isinstance(n, int) or isinstance(n, bool) or n < 1:
        raise ValueError("bad column")
    out = []
    while n:
        n, r = divmod(n - 1, 26)
        out.append(chr(65 + r))
    return "".join(reversed(out))
''',
        r'''import pytest
from solution import col_label as f
def test_a(): assert f(1) == 'A'
def test_z(): assert f(26) == 'Z'
def test_aa(): assert f(27) == 'AA'
def test_az(): assert f(52) == 'AZ'
def test_ba(): assert f(53) == 'BA'
def test_zz(): assert f(702) == 'ZZ'
def test_aaa(): assert f(703) == 'AAA'
def test_bad_zero():
    with pytest.raises(ValueError) as e: f(0)
    assert str(e.value) == 'bad column'
def test_bool():
    with pytest.raises(ValueError): f(True)
''',
        "hard", max_new_tokens=768),
    TaskSpec(
        "col_number",
        "Write a Python function col_number(s) that converts a spreadsheet column "
        "label into its 1-based column index and returns the integer. It is the "
        "inverse of the bijective base-26 labeling: A is 1, Z is 26, AA is 27, AZ "
        "is 52, ZZ is 702, AAA is 703. s must be a str, must be non-empty, and "
        "must consist only of uppercase ASCII letters A through Z; an empty "
        "string, any lowercase letter, any digit, and any other character each "
        "-> ValueError('bad label'). Output ONLY the function definition.",
        "solution.py",
        r'''def col_number(s):
    if not isinstance(s, str) or s == "":
        raise ValueError("bad label")
    val = 0
    for ch in s:
        if not ("A" <= ch <= "Z"):
            raise ValueError("bad label")
        val = val * 26 + (ord(ch) - 64)
    return val
''',
        r'''import pytest
from solution import col_number as f
def test_a(): assert f('A') == 1
def test_z(): assert f('Z') == 26
def test_aa(): assert f('AA') == 27
def test_az(): assert f('AZ') == 52
def test_zz(): assert f('ZZ') == 702
def test_aaa(): assert f('AAA') == 703
def test_empty():
    with pytest.raises(ValueError) as e: f('')
    assert str(e.value) == 'bad label'
def test_lower():
    with pytest.raises(ValueError): f('a')
def test_digit():
    with pytest.raises(ValueError): f('A1')
''',
        "hard", max_new_tokens=768),
    TaskSpec(
        "luhn_valid",
        "Write a Python function luhn_valid(s) that checks a string of decimal "
        "digits against the Luhn checksum and returns a bool. s must be a str, "
        "must be non-empty, and must contain only ASCII decimal digits; a "
        "non-string, an empty string, or any non-ASCII-digit character each -> "
        "ValueError('bad number'). The Luhn rule: walking from the rightmost "
        "digit leftward, leave digits in odd positions (the rightmost is position "
        "one, counted as position zero here) as they are and double the digit in "
        "every second position; a doubled digit greater than nine has nine "
        "subtracted from it. Sum all the resulting digits; the string is valid "
        "when that sum is a multiple of ten. Return True when valid, False "
        "otherwise. Output ONLY the function definition.",
        "solution.py",
        r'''def luhn_valid(s):
    if not isinstance(s, str) or s == "":
        raise ValueError("bad number")
    total = 0
    for i, ch in enumerate(reversed(s)):
        if not ch.isascii() or not ch.isdigit():
            raise ValueError("bad number")
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0
''',
        r'''import pytest
from solution import luhn_valid as f
def test_single_zero(): assert f('0') is True
def test_eighteen(): assert f('18') is True
def test_seventeen(): assert f('17') is False
def test_classic_valid(): assert f('79927398713') is True
def test_classic_invalid(): assert f('79927398710') is False
def test_twenty_six(): assert f('26') is True
def test_bad_char():
    with pytest.raises(ValueError) as e: f('12a')
    assert str(e.value) == 'bad number'
def test_empty():
    with pytest.raises(ValueError): f('')
def test_not_str():
    with pytest.raises(ValueError): f(18)
''',
        "hard", max_new_tokens=768),
    TaskSpec(
        "isbn10_check",
        "Write a Python function isbn10_check(s) that validates an ISBN-10 string "
        "and returns a bool. s must be a str of exactly ten characters; a "
        "non-string or any other length -> ValueError('bad isbn'). The first nine "
        "characters must be ASCII decimal digits. The tenth character is the check "
        "symbol: it is either an ASCII decimal digit or an uppercase letter X, "
        "where X stands for the value ten; a lowercase x is not accepted, and an X "
        "in any of the first nine positions is not accepted. Any character that "
        "breaks these rules -> ValueError('bad isbn'). Compute the weighted sum "
        "where the first character is multiplied by ten, the second by nine, and "
        "so on down to the tenth character multiplied by one; the string is valid "
        "when that sum is a multiple of eleven. Return True when valid, False "
        "otherwise. Output ONLY the function definition.",
        "solution.py",
        r'''def isbn10_check(s):
    if not isinstance(s, str) or len(s) != 10:
        raise ValueError("bad isbn")
    total = 0
    for i, ch in enumerate(s):
        if i == 9 and ch == "X":
            d = 10
        elif ch.isascii() and ch.isdigit():
            d = int(ch)
        else:
            raise ValueError("bad isbn")
        total += d * (10 - i)
    return total % 11 == 0
''',
        r'''import pytest
from solution import isbn10_check as f
def test_valid_digits(): assert f('0306406152') is True
def test_valid_x(): assert f('048665088X') is True
def test_invalid(): assert f('0306406153') is False
def test_bad_length():
    with pytest.raises(ValueError) as e: f('123')
    assert str(e.value) == 'bad isbn'
def test_lower_x():
    with pytest.raises(ValueError): f('048665088x')
def test_x_not_last():
    with pytest.raises(ValueError): f('X306406152')
def test_not_str():
    with pytest.raises(ValueError): f(123)
''',
        "hard", max_new_tokens=768),
    TaskSpec(
        "days_in_month",
        "Write a Python function days_in_month(year, month) that returns the "
        "number of days in a month of the proleptic Gregorian calendar. year must "
        "be an int, must not be a bool, and must be at least 1; otherwise -> "
        "ValueError('bad year'). month must be an int, must not be a bool, and "
        "must satisfy 1 <= month <= 12; otherwise -> ValueError('bad month'). "
        "April, June, September, and November have 30 days; the other non-February "
        "months have 31. February has 29 days in a leap year and 28 otherwise. A "
        "year is a leap year when it is divisible by four, except that years "
        "divisible by one hundred are not leap years unless they are also "
        "divisible by four hundred (so 1900 is common but 2000 is leap). Output "
        "ONLY the function definition.",
        "solution.py",
        r'''def days_in_month(year, month):
    if not isinstance(year, int) or isinstance(year, bool) or year < 1:
        raise ValueError("bad year")
    if not isinstance(month, int) or isinstance(month, bool) or month < 1 or month > 12:
        raise ValueError("bad month")
    if month == 2:
        leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
        return 29 if leap else 28
    return 30 if month in (4, 6, 9, 11) else 31
''',
        r'''import pytest
from solution import days_in_month as f
def test_leap_feb(): assert f(2020, 2) == 29
def test_century_common(): assert f(1900, 2) == 28
def test_century_leap(): assert f(2000, 2) == 29
def test_common_feb(): assert f(2021, 2) == 28
def test_april(): assert f(2021, 4) == 30
def test_january(): assert f(2021, 1) == 31
def test_december(): assert f(2021, 12) == 31
def test_bad_month_zero():
    with pytest.raises(ValueError) as e: f(2021, 0)
    assert str(e.value) == 'bad month'
def test_bad_month_high():
    with pytest.raises(ValueError): f(2021, 13)
def test_bad_year():
    with pytest.raises(ValueError) as e: f(0, 1)
    assert str(e.value) == 'bad year'
def test_bool_year():
    with pytest.raises(ValueError): f(True, 1)
''',
        "hard", max_new_tokens=768),
    TaskSpec(
        "ordinal_day",
        "Write a Python function ordinal_day(year, month, day) that returns the "
        "1-based day-of-year ordinal of a proleptic Gregorian date, so January 1 "
        "is 1 and December 31 is 365 in a common year or 366 in a leap year. "
        "Validation runs in this order, each failure its own ValueError with "
        "exactly the message. year must be an int, not a bool, at least 1 -> "
        "'bad year'. month must be an int, not a bool, in 1 through 12 -> 'bad "
        "month'. day must be an int, not a bool, at least 1, and at most the "
        "number of days that month actually has in that year (accounting for "
        "leap years, where a year is leap when divisible by four but not by one "
        "hundred unless also by four hundred) -> 'bad day'. So February 29 is "
        "valid only in a leap year. Output ONLY the function definition.",
        "solution.py",
        r'''def ordinal_day(year, month, day):
    if not isinstance(year, int) or isinstance(year, bool) or year < 1:
        raise ValueError("bad year")
    if not isinstance(month, int) or isinstance(month, bool) or month < 1 or month > 12:
        raise ValueError("bad month")
    leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
    mdays = [31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    if not isinstance(day, int) or isinstance(day, bool) or day < 1 or day > mdays[month - 1]:
        raise ValueError("bad day")
    return sum(mdays[:month - 1]) + day
''',
        r'''import pytest
from solution import ordinal_day as f
def test_first(): assert f(2021, 1, 1) == 1
def test_last_common(): assert f(2021, 12, 31) == 365
def test_last_leap(): assert f(2020, 12, 31) == 366
def test_leap_march(): assert f(2020, 3, 1) == 61
def test_common_march(): assert f(2021, 3, 1) == 60
def test_feb_end(): assert f(2021, 2, 28) == 59
def test_bad_day_leap():
    with pytest.raises(ValueError) as e: f(2021, 2, 29)
    assert str(e.value) == 'bad day'
def test_bad_day_zero():
    with pytest.raises(ValueError): f(2021, 1, 0)
def test_bad_month():
    with pytest.raises(ValueError) as e: f(2021, 13, 1)
    assert str(e.value) == 'bad month'
def test_bad_year():
    with pytest.raises(ValueError) as e: f(0, 1, 1)
    assert str(e.value) == 'bad year'
''',
        "hard", max_new_tokens=768),
    TaskSpec(
        "weekday_name",
        "Write a Python function weekday_name(year, month, day) that returns the "
        "English weekday name of a proleptic Gregorian date, one of the strings "
        "Monday, Tuesday, Wednesday, Thursday, Friday, Saturday, Sunday. Validate "
        "the date exactly as follows, each failure its own ValueError with exactly "
        "the message: year an int, not a bool, at least 1 -> 'bad year'; month an "
        "int, not a bool, in 1 through 12 -> 'bad month'; day an int, not a bool, "
        "at least 1 and at most the real length of that month in that year, with "
        "leap Februaries having 29 days under the usual divisible-by-four, "
        "except-hundreds, unless-four-hundreds rule -> 'bad day'. For reference "
        "January 1 of the year 2000 was a Saturday and January 1 of 1970 was a "
        "Thursday. Output ONLY the function definition.",
        "solution.py",
        r'''def weekday_name(year, month, day):
    if not isinstance(year, int) or isinstance(year, bool) or year < 1:
        raise ValueError("bad year")
    if not isinstance(month, int) or isinstance(month, bool) or month < 1 or month > 12:
        raise ValueError("bad month")
    leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
    mdays = [31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    if not isinstance(day, int) or isinstance(day, bool) or day < 1 or day > mdays[month - 1]:
        raise ValueError("bad day")
    t = [0, 3, 2, 5, 0, 3, 5, 1, 4, 6, 2, 4]
    y = year - 1 if month < 3 else year
    idx = (y + y // 4 - y // 100 + y // 400 + t[month - 1] + day) % 7
    names = ["Sunday", "Monday", "Tuesday", "Wednesday",
             "Thursday", "Friday", "Saturday"]
    return names[idx]
''',
        r'''import pytest
from solution import weekday_name as f
def test_millennium(): assert f(2000, 1, 1) == 'Saturday'
def test_2021(): assert f(2021, 1, 1) == 'Friday'
def test_epoch(): assert f(1970, 1, 1) == 'Thursday'
def test_leap_2024(): assert f(2024, 2, 29) == 'Thursday'
def test_leap_2016(): assert f(2016, 2, 29) == 'Monday'
def test_bad_day():
    with pytest.raises(ValueError) as e: f(2021, 2, 29)
    assert str(e.value) == 'bad day'
def test_bad_month():
    with pytest.raises(ValueError) as e: f(2021, 0, 1)
    assert str(e.value) == 'bad month'
def test_bad_year():
    with pytest.raises(ValueError) as e: f(0, 1, 1)
    assert str(e.value) == 'bad year'
''',
        "hard", max_new_tokens=768),
    TaskSpec(
        "days_between",
        "Write a Python function days_between(d1, d2) that returns the signed "
        "number of days from d1 to d2 (that is, d2 minus d1) as an int, positive "
        "when d2 is later, zero when equal, negative when earlier. Each argument "
        "must be EXACTLY a tuple of exactly three values (year, month, day), each "
        "an int and not a bool, forming a valid proleptic Gregorian date: year at "
        "least 1, month in 1 through 12, day at least 1 and at most the real "
        "length of that month in that year (leap Februaries have 29 days under the "
        "divisible-by-four, except-hundreds, unless-four-hundreds rule). Any "
        "violation in either argument -> ValueError('bad date'). Counting is by "
        "whole days: consecutive calendar days differ by one, and crossing a leap "
        "day counts. Output ONLY the function definition.",
        "solution.py",
        r'''def days_between(d1, d2):
    def check(dt):
        if type(dt) is not tuple or len(dt) != 3:
            raise ValueError("bad date")
        for v in dt:
            if not isinstance(v, int) or isinstance(v, bool):
                raise ValueError("bad date")
        y, m, d = dt
        if y < 1 or m < 1 or m > 12:
            raise ValueError("bad date")
        leap = y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)
        mdays = [31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
        if d < 1 or d > mdays[m - 1]:
            raise ValueError("bad date")

    def serial(dt):
        y, m, d = dt
        yy = y - (1 if m <= 2 else 0)
        era = yy // 400
        yoe = yy - era * 400
        doy = (153 * (m - 3 if m > 2 else m + 9) + 2) // 5 + d - 1
        doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
        return era * 146097 + doe - 719468

    check(d1)
    check(d2)
    return serial(d2) - serial(d1)
''',
        r'''import pytest
from solution import days_between as f
def test_same(): assert f((1970, 1, 1), (1970, 1, 1)) == 0
def test_next(): assert f((1970, 1, 1), (1970, 1, 2)) == 1
def test_prev(): assert f((1970, 1, 2), (1970, 1, 1)) == -1
def test_leap_cross(): assert f((2020, 2, 28), (2020, 3, 1)) == 2
def test_common_cross(): assert f((2019, 2, 28), (2019, 3, 1)) == 1
def test_leap_year_span(): assert f((2000, 1, 1), (2001, 1, 1)) == 366
def test_bad_date():
    with pytest.raises(ValueError) as e: f((2021, 2, 29), (2021, 3, 1))
    assert str(e.value) == 'bad date'
def test_not_tuple():
    with pytest.raises(ValueError): f([1970, 1, 1], (1970, 1, 2))
def test_bool():
    with pytest.raises(ValueError): f((1970, 1, 1), (1970, 1, True))
''',
        "hard", max_new_tokens=768),
    TaskSpec(
        "semver_compare",
        "Write a Python function semver_compare(a, b) that compares two semantic "
        "version strings and returns -1 if a has lower precedence than b, 0 if "
        "they have equal precedence, and 1 if a is higher. Each version must be "
        "three dot-separated numeric identifiers major.minor.patch, each a run of "
        "ASCII digits with no leading zero (except a lone 0), optionally followed "
        "by a hyphen and a pre-release made of one or more dot-separated "
        "identifiers. A pre-release identifier is either all ASCII digits with no "
        "leading zero, or a run of ASCII letters, digits, and hyphens containing "
        "at least one non-digit. Any deviation, including build metadata, an empty "
        "identifier, or a non-string -> ValueError('bad version'). Precedence "
        "rules: compare major, then minor, then patch as integers; a version with "
        "a pre-release ranks lower than the otherwise-equal version without one; "
        "when both have pre-releases compare their identifiers left to right, "
        "where a purely numeric identifier ranks lower than a non-numeric one, two "
        "numeric identifiers compare as integers, two non-numeric identifiers "
        "compare by ASCII order, and if all shared identifiers are equal the one "
        "with more identifiers ranks higher. Output ONLY the function definition.",
        "solution.py",
        r'''def semver_compare(a, b):
    import re

    def parse(s):
        if not isinstance(s, str):
            raise ValueError("bad version")
        m = re.fullmatch(
            r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-([0-9A-Za-z.-]+))?", s)
        if not m:
            raise ValueError("bad version")
        core = [int(m.group(1)), int(m.group(2)), int(m.group(3))]
        pre = m.group(4)
        ids = []
        if pre is not None:
            for part in pre.split("."):
                if part == "":
                    raise ValueError("bad version")
                if part.isdigit():
                    if len(part) > 1 and part[0] == "0":
                        raise ValueError("bad version")
                    ids.append((0, int(part), ""))
                else:
                    if not re.fullmatch(r"[0-9A-Za-z-]+", part):
                        raise ValueError("bad version")
                    ids.append((1, 0, part))
        return core, ids, pre is not None

    ca, ia, pa = parse(a)
    cb, ib, pb = parse(b)
    if ca != cb:
        return -1 if ca < cb else 1
    if not pa and not pb:
        return 0
    if pa and not pb:
        return -1
    if pb and not pa:
        return 1
    for x, y in zip(ia, ib):
        if x != y:
            return -1 if x < y else 1
    if len(ia) != len(ib):
        return -1 if len(ia) < len(ib) else 1
    return 0
''',
        r'''import pytest
from solution import semver_compare as f
def test_equal(): assert f('1.0.0', '1.0.0') == 0
def test_major(): assert f('1.0.0', '2.0.0') == -1
def test_major_gt(): assert f('2.0.0', '1.0.0') == 1
def test_patch(): assert f('1.0.0', '1.0.1') == -1
def test_pre_lt_release(): assert f('1.0.0-alpha', '1.0.0') == -1
def test_more_ids(): assert f('1.0.0-alpha', '1.0.0-alpha.1') == -1
def test_numeric_lt_alpha(): assert f('1.0.0-alpha.1', '1.0.0-alpha.beta') == -1
def test_ascii_order(): assert f('1.0.0-alpha.beta', '1.0.0-beta') == -1
def test_numeric_ids(): assert f('1.0.0-beta.2', '1.0.0-beta.11') == -1
def test_bad_two_parts():
    with pytest.raises(ValueError) as e: f('1.0', '1.0.0')
    assert str(e.value) == 'bad version'
def test_bad_leading_zero():
    with pytest.raises(ValueError): f('01.0.0', '1.0.0')
def test_bad_pre_leading_zero():
    with pytest.raises(ValueError): f('1.0.0-01', '1.0.0')
''',
        "hard", max_new_tokens=768),
    TaskSpec(
        "natural_compare",
        "Write a Python function natural_compare(a, b) that compares two strings "
        "in natural (human) order and returns -1, 0, or 1. Both arguments must be "
        "strings; otherwise -> ValueError('bad input'). Split each string into a "
        "sequence of maximal runs that alternate between runs of ASCII digits and "
        "runs of non-digit characters. Compare the two sequences run by run: if "
        "one run is a digit run and the aligned run is a non-digit run, the digit "
        "run compares as smaller; two digit runs compare first by integer value, "
        "and if the values are equal the run with fewer characters (fewer leading "
        "zeros) compares as smaller; two non-digit runs compare by ASCII order of "
        "their characters. If all aligned runs are equal but one sequence has more "
        "runs, the shorter sequence compares as smaller. Only equal-length "
        "sequences that match run for run give 0. Output ONLY the function "
        "definition.",
        "solution.py",
        r'''def natural_compare(a, b):
    if not isinstance(a, str) or not isinstance(b, str):
        raise ValueError("bad input")

    def toks(s):
        out = []
        i, n = 0, len(s)
        while i < n:
            j = i
            if s[i].isascii() and s[i].isdigit():
                while j < n and s[j].isascii() and s[j].isdigit():
                    j += 1
                out.append((0, int(s[i:j]), j - i, ""))
            else:
                while j < n and not (s[j].isascii() and s[j].isdigit()):
                    j += 1
                out.append((1, 0, 0, s[i:j]))
            i = j
        return out

    ta, tb = toks(a), toks(b)
    for x, y in zip(ta, tb):
        if x[0] != y[0]:
            return -1 if x[0] < y[0] else 1
        if x[0] == 0:
            if x[1] != y[1]:
                return -1 if x[1] < y[1] else 1
            if x[2] != y[2]:
                return -1 if x[2] < y[2] else 1
        elif x[3] != y[3]:
            return -1 if x[3] < y[3] else 1
    if len(ta) != len(tb):
        return -1 if len(ta) < len(tb) else 1
    return 0
''',
        r'''import pytest
from solution import natural_compare as f
def test_numeric(): assert f('a2', 'a10') == -1
def test_numeric_gt(): assert f('a10', 'a2') == 1
def test_file(): assert f('file9', 'file10') == -1
def test_equal(): assert f('abc', 'abc') == 0
def test_prefix(): assert f('a', 'a1') == -1
def test_leading_zero(): assert f('01', '1') == 1
def test_digit_before_alpha(): assert f('1', 'a') == -1
def test_plain_alpha(): assert f('a', 'b') == -1
def test_bad_input():
    with pytest.raises(ValueError) as e: f(1, 'a')
    assert str(e.value) == 'bad input'
''',
        "hard", max_new_tokens=768),
    TaskSpec(
        "percent_decode",
        "Write a Python function percent_decode(s) that decodes a "
        "percent-encoded ASCII string and returns the decoded string. s must be a "
        "str; otherwise -> ValueError('bad input'). A percent sign introduces an "
        "escape and must be followed by exactly two hexadecimal digits (0 through "
        "9 and a through f in either case); the two digits name a byte value. If a "
        "percent sign is not followed by two hexadecimal digits (including a "
        "percent sign at or near the end of the string) -> "
        "ValueError('bad escape'). If the named byte value is 128 or greater "
        "(outside 7-bit ASCII) -> ValueError('non-ascii byte'). Otherwise the byte "
        "becomes the character with that code point. A plus sign is a literal plus "
        "sign, NOT a space, in this decoder. Every other character is copied "
        "through unchanged. Output ONLY the function definition.",
        "solution.py",
        r'''def percent_decode(s):
    if not isinstance(s, str):
        raise ValueError("bad input")
    hexd = "0123456789abcdefABCDEF"
    out = []
    i, n = 0, len(s)
    while i < n:
        c = s[i]
        if c == "%":
            if i + 2 >= n or s[i + 1] not in hexd or s[i + 2] not in hexd:
                raise ValueError("bad escape")
            b = int(s[i + 1:i + 3], 16)
            if b >= 128:
                raise ValueError("non-ascii byte")
            out.append(chr(b))
            i += 3
        else:
            out.append(c)
            i += 1
    return "".join(out)
''',
        r'''import pytest
from solution import percent_decode as f
def test_space(): assert f('a%20b') == 'a b'
def test_upper_hex(): assert f('%41') == 'A'
def test_percent_literal(): assert f('100%25') == '100%'
def test_plus_literal(): assert f('a+b') == 'a+b'
def test_plain(): assert f('hello') == 'hello'
def test_mixed_case(): assert f('%2F%2f') == '//'
def test_short_escape():
    with pytest.raises(ValueError) as e: f('a%2')
    assert str(e.value) == 'bad escape'
def test_nonhex():
    with pytest.raises(ValueError) as e: f('%2g')
    assert str(e.value) == 'bad escape'
def test_non_ascii():
    with pytest.raises(ValueError) as e: f('%80')
    assert str(e.value) == 'non-ascii byte'
def test_lone_percent():
    with pytest.raises(ValueError): f('%')
''',
        "hard", max_new_tokens=768),
    TaskSpec(
        "csv_quote",
        "Write a Python function csv_quote(field) that encodes a single CSV field "
        "in the RFC 4180 style and returns the encoded string. field must be a "
        "str; otherwise -> ValueError('bad field'). The field must be quoted if "
        "and only if it contains at least one of these four characters: a comma, "
        "a double quote, a carriage return, or a line feed. To quote a field, "
        "wrap the whole field in double quotes and double every double-quote "
        "character that appears inside it. A field with none of those four "
        "characters is returned exactly as-is, including when it contains spaces "
        "or is empty (the empty string returns the empty string, never a pair of "
        "quotes). Output ONLY the function definition.",
        "solution.py",
        r'''def csv_quote(field):
    if not isinstance(field, str):
        raise ValueError("bad field")
    if any(c in field for c in (",", '"', "\r", "\n")):
        return '"' + field.replace('"', '""') + '"'
    return field
''',
        r'''import pytest
from solution import csv_quote as f
def test_plain(): assert f('abc') == 'abc'
def test_comma(): assert f('a,b') == '"a,b"'
def test_quote(): assert f('a"b') == '"a""b"'
def test_newline(): assert f('a\nb') == '"a\nb"'
def test_empty(): assert f('') == ''
def test_only_quote(): assert f('"') == '""""'
def test_space_plain(): assert f('a b') == 'a b'
def test_carriage(): assert f('a\rb') == '"a\rb"'
def test_bad_field():
    with pytest.raises(ValueError) as e: f(5)
    assert str(e.value) == 'bad field'
''',
        "hard", max_new_tokens=768),
    TaskSpec(
        "round_half_even",
        "Write a Python function round_half_even(num, den) that rounds the exact "
        "rational number num divided by den to the nearest integer using "
        "round-half-to-even (banker's rounding) and returns that int. Both "
        "arguments must be ints and not bools; otherwise -> ValueError('bad "
        "arg'). den must not be zero; otherwise -> ValueError('div by zero'). The "
        "sign of den is handled correctly, so the result of num over den has the "
        "usual mathematical sign regardless of which operand is negative. When the "
        "exact value is not a half-integer, round to the nearer integer. When it "
        "is exactly halfway between two integers, round to whichever of the two is "
        "even. So 1/2 rounds to 0, 3/2 rounds to 2, 5/2 rounds to 2, and -1/2 "
        "rounds to 0. Output ONLY the function definition.",
        "solution.py",
        r'''def round_half_even(num, den):
    for v in (num, den):
        if not isinstance(v, int) or isinstance(v, bool):
            raise ValueError("bad arg")
    if den == 0:
        raise ValueError("div by zero")
    if den < 0:
        num, den = -num, -den
    q, r = divmod(num, den)
    twice = 2 * r
    if twice < den:
        return q
    if twice > den:
        return q + 1
    return q if q % 2 == 0 else q + 1
''',
        r'''import pytest
from solution import round_half_even as f
def test_half_down(): assert f(1, 2) == 0
def test_half_up(): assert f(3, 2) == 2
def test_half_even(): assert f(5, 2) == 2
def test_over(): assert f(7, 4) == 2
def test_third(): assert f(1, 3) == 0
def test_neg_half(): assert f(-1, 2) == 0
def test_neg_three_half(): assert f(-3, 2) == -2
def test_exact(): assert f(4, 2) == 2
def test_neg_den(): assert f(5, -2) == -2
def test_div_zero():
    with pytest.raises(ValueError) as e: f(1, 0)
    assert str(e.value) == 'div by zero'
def test_bad_arg():
    with pytest.raises(ValueError) as e: f(True, 2)
    assert str(e.value) == 'bad arg'
''',
        "hard", max_new_tokens=768),
    TaskSpec(
        "reverse_bits",
        "Write a Python function reverse_bits(n, width) that reverses the order of "
        "the low `width` bits of a non-negative integer and returns the resulting "
        "integer. Both arguments must be ints and not bools; otherwise -> "
        "ValueError('bad arg'). width must be at least 1 and n must be at least 0; "
        "a width below 1 or a negative n -> ValueError('bad arg'). n must fit in "
        "width bits, meaning n must be strictly less than two to the power width; "
        "otherwise -> ValueError('overflow'). Treat n as exactly width bits (the "
        "most significant of those bits may be zero) and reverse their order, so "
        "the least significant bit becomes the most significant. For example with "
        "width 8 the value 1 becomes 128, and with width 4 the value binary 1010 "
        "becomes binary 0101. Output ONLY the function definition.",
        "solution.py",
        r'''def reverse_bits(n, width):
    for v in (n, width):
        if not isinstance(v, int) or isinstance(v, bool):
            raise ValueError("bad arg")
    if width < 1 or n < 0:
        raise ValueError("bad arg")
    if n >= (1 << width):
        raise ValueError("overflow")
    r = 0
    for _ in range(width):
        r = (r << 1) | (n & 1)
        n >>= 1
    return r
''',
        r'''import pytest
from solution import reverse_bits as f
def test_one_eight(): assert f(1, 8) == 128
def test_ten_four(): assert f(0b1010, 4) == 0b0101
def test_zero(): assert f(0, 4) == 0
def test_six_three(): assert f(0b110, 3) == 0b011
def test_one_one(): assert f(1, 1) == 1
def test_all_ones(): assert f(0b1111, 4) == 0b1111
def test_overflow():
    with pytest.raises(ValueError) as e: f(16, 4)
    assert str(e.value) == 'overflow'
def test_bad_width():
    with pytest.raises(ValueError) as e: f(1, 0)
    assert str(e.value) == 'bad arg'
def test_bad_neg():
    with pytest.raises(ValueError): f(-1, 4)
def test_bool():
    with pytest.raises(ValueError): f(True, 4)
''',
        "hard", max_new_tokens=768),
    TaskSpec(
        "reduce_fraction",
        "Write a Python function reduce_fraction(num, den) that reduces a fraction "
        "to lowest terms and returns it as a tuple (numerator, denominator). Both "
        "arguments must be ints and not bools; otherwise -> ValueError('bad "
        "arg'). den must not be zero; otherwise -> ValueError('div by zero'). "
        "Divide both parts by their greatest common divisor. The returned "
        "denominator is always strictly positive, so any negative sign is carried "
        "on the numerator (a fraction like 4 over -8 reduces to -1 over 2). A zero "
        "numerator always reduces to the tuple (0, 1) regardless of the "
        "denominator. Output ONLY the function definition.",
        "solution.py",
        r'''def reduce_fraction(num, den):
    for v in (num, den):
        if not isinstance(v, int) or isinstance(v, bool):
            raise ValueError("bad arg")
    if den == 0:
        raise ValueError("div by zero")
    if num == 0:
        return (0, 1)
    from math import gcd
    g = gcd(abs(num), abs(den))
    num //= g
    den //= g
    if den < 0:
        num, den = -num, -den
    return (num, den)
''',
        r'''import pytest
from solution import reduce_fraction as f
def test_basic(): assert f(4, 8) == (1, 2)
def test_neg_num(): assert f(-4, 8) == (-1, 2)
def test_neg_den(): assert f(4, -8) == (-1, 2)
def test_both_neg(): assert f(-4, -8) == (1, 2)
def test_zero(): assert f(0, 5) == (0, 1)
def test_already(): assert f(7, 1) == (7, 1)
def test_reduce_int(): assert f(6, 3) == (2, 1)
def test_div_zero():
    with pytest.raises(ValueError) as e: f(1, 0)
    assert str(e.value) == 'div by zero'
def test_bad_arg():
    with pytest.raises(ValueError) as e: f(True, 2)
    assert str(e.value) == 'bad arg'
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
