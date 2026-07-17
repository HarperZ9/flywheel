def add_months(year: int, month: int, day: int, n: int) -> tuple[int, int, int]:
    if not all(isinstance(v, int) and not isinstance(v, bool)
               for v in (year, month, day, n)):
        raise ValueError("all arguments must be ints")
    if year < 1:
        raise ValueError(f"invalid year {year}: must be >= 1")
    if not (1 <= month <= 12):
        raise ValueError(f"month {month} out of range; must be in [1, 12]")
    _days_in_month = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    def days_in(year: int, month: int) -> int:
        d = _days_in_month[month - 1]
        if month == 2 and (year % 400 == 0 or (year % 4 == 0 and year % 100 != 0)):
            return d + 1
        return d
    if not (1 <= day <= days_in(year, month)):
        raise ValueError(f"day {day} out of range for {year}-{month:02}")
    y = year + n // 12
    m = month + n % 12
    while m > 12:
        m -= 12
        y += 1
    while m < 1:
        m += 12
        y -= 1
    if y < 1:
        raise ValueError(f"resulting year {y} would be below 1")
    return (y, m, min(day, days_in(y, m)))
