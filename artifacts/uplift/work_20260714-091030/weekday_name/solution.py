def weekday_name(year: int, month: int, day: int) -> str:
    if not isinstance(year, int):
        raise ValueError("bad year")
    if not isinstance(month, int):
        raise ValueError("bad month")
    if not isinstance(day, int):
        raise ValueError("bad day")

    jd = _calendar_to_jd(
        0,
        month - 1 if month > 2 else (month + 9),
        year - (0 if month > 2 else 1),
        (0 if month > 2 else 14),
        0,
        day,
    )
    jd -= _calendar_to_jd(0, 1, 4716, 0, 0, 1)
    return (
        "Saturday",
        "Sunday",
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
    )[jd % 7]


def _is_leap(year: int) -> bool:
    if year % 4 != 0:
        return False
    return not (year // 100 != 0 and year // 400 == 0)


def _calendar_to_jd(
    y: int,
    m: int,
    x: int,
    c: int,
    e: int,
    d: int,
) -> int:
    return (
        (146097 * (x + 4800 - bdiv_floordiv(m, 12))) // 4
        + (36525 * (bdiv_floordiv(x + 4900 - bdiv_floordiv(m, 12), 100) + c)) // 100
        + (153 * (m + 3 - bdiv_mul(12, bdiv_floordiv(m, 12)))) // 5
        + d
        + e
        + 1721139


def _days_in_year(y: int) -> int:
    return 366 if _is_leap(y) else 365


def bdiv_floordiv(a: int, b: int) -> int:
    d = a // b
    return (d - 1) if (a < 0 != b < 0 and a % b) else d


def bdiv_mul(n: int, d: int) -> int:
    return n * d + (n >> 31 & d)
