#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
articulate.quantities -- numbers, units, dates, times, and versions as invariants.

`find(text)` returns (start, end, key) for every quantity in the text. The key is
normalized so a faithful reformatting compares equal: "10 ms" and "10ms",
"50%" and "50 percent", "1,000" and "1000", "three" and "3", "May 5, 2026" and
"2026-05-05", "2:00 PM" and "2pm", "v1.2.3" and "1.2.3", "one million" and
"1000000", "$5M" and "$5 million", "10 megabytes" and "10 MB", "20 dollars" and
"$20". A change of value or unit changes the key. A plural magnitude
("thousands") keys as itself.

Limits, stated plainly. The word "one" is skipped unless a magnitude word follows
("one million"), since it is far more often a pronoun. Ordinal words ("first")
are skipped. A spaced single-letter unit ("10 m") reads as a bare number, since
the letter could be a word. "pounds" names a weight or a currency, so it keys as
its own unit and matches neither "lb" nor "\u00a3". A slash date keeps its raw
form, because 5/9 names different days in different countries. Standard library
only.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation, localcontext

_MONTH = (r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?"
          r"|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)")
_MONTH_NUM = {m: i for i, m in enumerate(
    ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov",
     "dec"), 1)}
_WORDS = {w: i for i, w in enumerate(
    ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
     "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
     "seventeen", "eighteen", "nineteen"))}
_WORDS.update({w: 10 * i for i, w in enumerate(
    ("twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"), 2)})
_MULT = {"hundred": 10 ** 2, "thousand": 10 ** 3, "million": 10 ** 6,
         "billion": 10 ** 9, "trillion": 10 ** 12, "k": 10 ** 3, "dozen": 12,
         # The magnitude letters of a currency amount: $5M, $5bn, $2B.
         "m": 10 ** 6, "mn": 10 ** 6, "b": 10 ** 9, "bn": 10 ** 9, "t": 10 ** 12,
         "tn": 10 ** 12}
_MAG_RX = r"hundred|thousand|million|billion|trillion|dozen"
_WORD_RX = "|".join(sorted((w for w in _WORDS if w != "one"), key=len, reverse=True))
_UNIT_RX = "|".join(("one", "two", "three", "four", "five", "six", "seven", "eight",
                     "nine"))

# Canonical unit spellings, looked up in lower case. A symbol not listed keeps
# its own spelling, so "MB" (megabytes) and "Mb" (megabits) stay distinct. A
# unit spelled as a word maps to its symbol, so "10 megabytes" matches "10 MB".
_UNIT_CANON = {
    "percent": "%", "per cent": "%", "%": "%",
    "ms": "ms", "msec": "ms", "millisecond": "ms", "milliseconds": "ms",
    "us": "us", "\u00b5s": "us", "\u03bcs": "us", "microsecond": "us",
    "microseconds": "us", "ns": "ns", "nanosecond": "ns", "nanoseconds": "ns",
    "s": "s", "sec": "s", "secs": "s", "second": "s", "seconds": "s",
    "min": "min", "mins": "min", "minute": "min", "minutes": "min",
    "h": "h", "hr": "h", "hrs": "h", "hour": "h", "hours": "h",
    "d": "d", "day": "d", "days": "d", "week": "wk", "weeks": "wk",
    "month": "mo", "months": "mo", "year": "yr", "years": "yr", "yr": "yr",
    "yrs": "yr", "byte": "B", "bytes": "B", "bit": "bit", "bits": "bit",
    "kilobyte": "KB", "kilobytes": "KB", "megabyte": "MB", "megabytes": "MB",
    "gigabyte": "GB", "gigabytes": "GB", "terabyte": "TB", "terabytes": "TB",
    "petabyte": "PB", "petabytes": "PB", "kilobit": "kb", "kilobits": "kb",
    "megabit": "Mb", "megabits": "Mb", "gigabit": "Gb", "gigabits": "Gb",
    "hertz": "Hz", "kilohertz": "kHz", "megahertz": "MHz", "gigahertz": "GHz",
    "meter": "m", "meters": "m", "metre": "m", "metres": "m", "kilometer": "km",
    "kilometers": "km", "kilometre": "km", "kilometres": "km", "centimeter": "cm",
    "centimeters": "cm", "centimetre": "cm", "centimetres": "cm",
    "millimeter": "mm", "millimeters": "mm", "millimetre": "mm", "millimetres": "mm",
    "mile": "mi", "miles": "mi", "foot": "ft", "feet": "ft", "inch": "in",
    "inches": "in", "yard": "yd", "yards": "yd", "gram": "g", "grams": "g",
    "kilogram": "kg", "kilograms": "kg", "milligram": "mg", "milligrams": "mg",
    "ounce": "oz", "ounces": "oz", "lb": "lb", "lbs": "lb", "ton": "ton",
    "tons": "ton", "tonne": "t", "tonnes": "t",
    # "pound" names a weight or a currency, so it keeps a unit of its own.
    "pound": "pound", "pounds": "pound", "cent": "\u00a2", "cents": "\u00a2",
    # A currency word or code becomes the sign in front of the amount, where the
    # sign names that one currency. "$" can be any dollar, so USD stays a code.
    "dollar": "$", "dollars": "$", "euro": "\u20ac", "euros": "\u20ac",
    "eur": "\u20ac", "gbp": "\u00a3", "yen": "\u00a5",
}
_SIGNS = frozenset("$\u20ac\u00a3\u00a5")
_ATTACHED = sorted(
    ("ms", "us", "\u00b5s", "\u03bcs", "ns", "s", "min", "h", "hr", "hrs", "d", "KiB",
     "MiB", "GiB", "TiB", "PiB", "EiB", "KB", "MB", "GB", "TB", "PB", "EB", "kB", "kb",
     "Mb", "Gb", "B", "Hz", "kHz", "MHz", "GHz", "mm", "cm", "km", "m", "kg", "mg", "g",
     "lb", "lbs", "oz", "ft", "ml", "mL", "L", "px", "pt", "em", "rem", "x", "fps",
     "rpm", "W", "kW", "V", "mAh", "k", "K"), key=len, reverse=True)
# The units read after a space: these symbols, plus every lowercase word of three
# or more letters in _UNIT_CANON. A single letter after a space could be a word
# ("10 m"), so a one-letter unit reads only attached. Longest first, then by
# spelling, so the pattern is the same in every process.
_SPACED = sorted(
    {r"per\s{1,2}cent", "ms", "us", "\u00b5s", "\u03bcs", "ns", "KiB", "MiB", "GiB",
     "TiB", "PiB", "EiB", "KB", "kB", "MB", "GB", "TB", "PB", "EB", "kb", "Mb", "Gb",
     "kbps", "Mbps", "Gbps", "Hz", "kHz", "MHz", "GHz", "mm", "cm", "km", "kg", "mg",
     "oz", "ft", "ml", "px", "fps", "rpm", "kW", "mAh", "USD", "EUR", "GBP"}
    | {w for w in _UNIT_CANON if w.isalpha() and w.islower() and len(w) >= 3},
    key=lambda w: (-len(w), w))

_CORE = (r"(?<![\w.])(?P<sign>[-\u2212](?=[$\u20ac\u00a3\u00a5\d]))?"
         r"(?P<cur>[$\u20ac\u00a3\u00a5])?"
         r"(?P<digits>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
         rf"|(?P<word>(?i:\b(?:{_WORD_RX})(?:-(?:{_UNIT_RX}))?\b))"
         # "one", "a", or "an" is a number only before a magnitude word.
         rf"|(?P<one>(?i:\b(?:one|an?)\b)(?=\s{{1,3}}(?i:{_MAG_RX})\b))")
_TAIL = (rf"(?P<mult>(?i:\s{{1,3}}(?:{_MAG_RX})\b))?"
         # A magnitude letter counts only after a currency sign, so "$5M" is five
         # million and a bare "5B" stays five bytes.
         r"(?:(?(cur)(?P<cmult>mn|bn|tn|[MmBbT])\b|(?!))"
         r"|\s?(?P<pct>%)"
         rf"|(?P<att>{'|'.join(_ATTACHED)})\b"
         rf"|\s{{1,2}}(?P<spaced>°[CF]|(?:{'|'.join(_SPACED)})\b))?")
_QUANTITY = re.compile(
    rf"(?P<iso>\b\d{{4}}-\d{{2}}-\d{{2}}(?:[T ]\d{{2}}:\d{{2}}(?::\d{{2}})?)?\b)"
    rf"|(?P<mdy>\b{_MONTH}\.?\s{{1,3}}\d{{1,2}}(?:st|nd|rd|th)?\b(?:,?\s{{1,3}}\d{{4}}\b)?)"
    rf"|(?P<dmy>\b\d{{1,2}}(?:st|nd|rd|th)?\s{{1,3}}{_MONTH}\b\.?(?:,?\s{{1,3}}\d{{4}}\b)?)"
    rf"|(?P<my>\b{_MONTH}\.?\s{{1,3}}\d{{4}}\b)"
    r"|(?P<ver>\b[vV]?\d{1,6}(?:\.\d{1,6}){2,3}(?:[-+][0-9A-Za-z.\-]{1,40})?\b"
    r"|\b[vV]\d{1,6}(?:\.\d{1,6})?\b)"
    r"|(?P<slash>\b\d{1,4}/\d{1,2}(?:/\d{2,4})?\b)"
    r"|(?P<time>\b\d{1,2}:\d{2}(?::\d{2})?(?:\s?[AaPp]\.?[Mm]\b\.?)?)"
    # A clock time with no minutes: "2am", "2 PM", "2 p.m.".
    r"|(?P<clock>\b\d{1,2}\s?(?i:[ap]\.m\.|[ap]m\b))"
    r"|(?P<ord>\b\d{1,9}(?:st|nd|rd|th)\b)"
    # A plural magnitude is a size with no exact value: "thousands of users".
    r"|(?P<approx>(?i:\b(?:dozens|hundreds|thousands|millions|billions|trillions)\b))"
    rf"|(?:{_CORE}){_TAIL}")


# A 12-hour time on the hour: "2:00 PM" names the same time as "2 PM". A 24-hour
# "14:00" keeps its minutes, since "14" alone reads as a count.
_ON_THE_HOUR = re.compile(r"^(\d{1,2}):00(?=[ap]m$)")


def _date_key(m):
    """Normalize a month-name date to ISO order: YYYY-MM-DD, MM-DD, or YYYY-MM."""
    raw = m.group(0)
    month = _MONTH_NUM[re.search(_MONTH, raw).group(0)[:3].lower()]
    nums = re.findall(r"\d+", raw)
    year = next((n for n in nums if len(n) == 4), None)
    day = next((n for n in nums if len(n) <= 2), None)
    parts = [year] if year else []
    parts.append(f"{month:02d}")
    if day:
        parts.append(f"{int(day):02d}")
    return "date:" + "-".join(parts)


def _value(m):
    """The numeric value as a string. Digits keep their written precision; a
    multiplied value is computed exactly with Decimal."""
    if m.group("word"):
        parts = m.group("word").lower().split("-")
        base = Decimal(sum(_WORDS[p] for p in parts))
    elif m.group("one"):
        base = Decimal(1)
    else:
        base = Decimal(m.group("digits").replace(",", ""))
    mult = (m.group("mult") or "").strip().lower()
    att = m.group("att") or ""
    if att in ("k", "K"):
        mult = "k"
    if m.group("cmult"):
        mult = m.group("cmult").lower()
    if not mult and m.group("digits"):
        return m.group("digits").replace(",", "")
    # Decimal's default precision is 28 digits. Use enough precision for the
    # entire coefficient and multiplier, including normalize(), so changing a
    # late digit cannot disappear through rounding.
    multiplier = _MULT[mult] if mult else 1
    with localcontext() as context:
        context.prec = len(base.as_tuple().digits) + len(str(multiplier)) + 2
        base *= multiplier
        return format(base.normalize(), "f")


def _quantity_key(m):
    raw = m.group(0)
    if m.group("iso"):
        return "date:" + raw.replace(" ", "T")
    if m.group("mdy") or m.group("dmy") or m.group("my"):
        return _date_key(m)
    if m.group("ver"):
        return "version:" + raw.lstrip("vV")
    if m.group("time") or m.group("clock"):
        return "time:" + _ON_THE_HOUR.sub(r"\1", re.sub(r"[\s.]", "", raw).lower())
    if m.group("slash") or m.group("ord"):
        return raw
    if m.group("approx"):
        return "approx:" + raw.lower()
    try:
        value = _value(m)
    except (InvalidOperation, KeyError, ValueError):
        return raw
    unit = m.group("pct") or m.group("spaced") or m.group("att") or ""
    unit = "" if unit in ("k", "K") else unit
    unit = _UNIT_CANON.get(re.sub(r"\s+", " ", unit.lower()), unit)
    cur = m.group("cur") or ""
    if unit in _SIGNS and cur in ("", unit):
        cur, unit = unit, ""
    sign = "-" if m.group("sign") else ""
    return f"{sign}{cur}{value}{unit}"


def find(text):
    """(start, end, key) for each quantity in `text`, in document order."""
    out = []
    for m in _QUANTITY.finditer(text):
        if m.group(0).strip():
            out.append((m.start(), m.end(), _quantity_key(m)))
    return out
