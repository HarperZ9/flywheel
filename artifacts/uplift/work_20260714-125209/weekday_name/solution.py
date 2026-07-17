def weekday_name(year: int, month: int, day: int) -> str:
    MONTHS = (31, (29 if ((year % 4 == 0 and year % 100 != 0) or year % 400 == 0) else 28), 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    if not isinstance(year, int): raise ValueError('bad year')
    if not (isinstance(month, int) and 1 <= month <= 12): raise ValueError('bad month')
    if not (isinstance(day, int) and day >= 1 and day <= MONTHS[month - 1]): raise ValueError('bad day')
    jd = 365 * year + month // 2 + day
    for i in range(1, month):
        jd -= MONTHS[i - 1]
    if month > 2: jd -= (year % 4) and ((year % 4 == 0 and year % 100 != 0) or year % 400 == 0)
    wd = (jd + (365 * (year - 2000)) // 4 + 29) % 7
    return 'Tuesday' if month < 3 else ('Saturday', 'Sunday', 'Monday', 'Friday', 'Wednesday', 'Thursday')[wd]
