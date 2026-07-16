def add_months(year: int, month: int, day: int, n: int) -> tuple:
    if not all(isinstance(arg, int) and arg >= 0 for arg in (year, month, day, n)):
        raise ValueError("All arguments must be integers.")
    
    def is_leap_year(y):
        return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)
    
    days_in_month = [0, 31, 28 if not is_leap_year(year) else 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    
    month += n
    while month > 12:
        year += 1
        month -= 12
    while month < 1:
        year -= 1
        month += 12
    
    if day == days_in_month[month] and (day == days_in_month[month + 1] or month == 2 and is_leap_year(year)):
        day = days_in_month[month]
    
    while not (1 <= month <= 12) or (days_in_month[month] < day):
        if days_in_month[month] < day:
            day -= 1
        else:
            year += 1
            for _ in range(1, 13 - month):
                month = 0 if month == 0 else month - 1
            month += 12

    return (year, month, day)
