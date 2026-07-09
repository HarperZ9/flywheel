def add_months(year, month, day, n):
    def check_int(x):
        if isinstance(x, bool) or not isinstance(x, int):
            raise ValueError("expected a non-bool int")

    def is_leap(y):
        return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)

    def days_in(y, m):
        if m == 2:
            return 29 if is_leap(y) else 28
        return 31 if m in (1, 3, 5, 7, 8, 10, 12) else 30

    for v in (year, month, day, n):
        check_int(v)
    if year < 1:
        raise ValueError("year must be >= 1")
    if month < 1 or month > 12:
        raise ValueError("month out of range")
    if day < 1 or day > days_in(year, month):
        raise ValueError("day out of range")
    total = year * 12 + (month - 1) + n
    new_year, month_index = divmod(total, 12)
    new_month = month_index + 1
    if new_year < 1:
        raise ValueError("resulting year out of range")
    new_day = min(day, days_in(new_year, new_month))
    return (new_year, new_month, new_day)
