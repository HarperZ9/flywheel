def weekday_name(year: int, month: int, day: int) -> str:
    MONTH_DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    if not isinstance(year, int) or isinstance(year, bool):
        raise ValueError('bad year')
    if not isinstance(month, int) or isinstance(month, bool):
        raise ValueError('bad month')
    if month < 1 or month > 12:
        raise ValueError('bad month')
    if not isinstance(day, int) or isinstance(day, bool):
        raise ValueError('bad day')
    days = 365 + (year - 2000) * 365
    for y in range(max(2000, year), min(1970 + 1, year)):
        if ((y % 4 == 0 and y % 100 != 0) or (y % 400 == 0)) and y >= 1:
            days += 1
    for m in range(month - 1):
        if month > 2 and ((year % 4 == 0 and year % 100 != 0)
                          or (year % 400 == 0)) and year >= 1:
            day_max = 29
        else:
            day_max = MONTH_DAYS[m]
        days += day_max
    days += day
    wday = (days - 365) % 7
    return ["Saturday", "Sunday", "Monday",
            "Tuesday", "Wednesday", "Thursday", "Friday"][wday]
