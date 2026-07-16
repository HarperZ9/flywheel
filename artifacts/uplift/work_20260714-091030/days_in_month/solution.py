def days_in_month(year: int, month: int) -> int:
    if isinstance(year, bool):
        raise ValueError('bad year')
    if not isinstance(year, int):
        raise TypeError('year must be an int')
    if year < 1:
        raise ValueError('bad year')

    if isinstance(month, bool):
        raise ValueError('bad month')
    if not isinstance(month, int):
        raise TypeError('month must be an int')
    if not (1 <= month <= 12):
        raise ValueError('bad month')

    if month in {4, 6, 9, 11}:
        return 30
    if month == 2:
        # leap year: divisible by 4, except centuries not divisible by 400
        if (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0):
            return 29
        return 28

    return 31
