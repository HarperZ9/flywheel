def ordinal_day(year, month, day):
    if not isinstance(year, int) or isinstance(year, bool):
        raise ValueError('bad year')
    if not (1 <= year):
        raise ValueError('bad year')
    if not isinstance(month, int) or isinstance(month, bool):
        raise ValueError('bad month')
    if not (1 <= month <= 12):
        raise ValueError('bad month')
    if not isinstance(day, int) or isinstance(day, bool):
        raise ValueError('bad day')
    if not (1 <= day):
        raise ValueError('bad day')
    days_in_month = [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    if not (1 <= day <= days_in_month[month - 1]):
        raise ValueError('bad day')
    return sum(days_in_month[:month - 1]) + day
