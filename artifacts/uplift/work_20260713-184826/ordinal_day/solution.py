def ordinal_day(year, month, day):
    if not isinstance(year, int):
        raise ValueError('bad year')
    if not isinstance(month, int):
        raise ValueError('bad month')
    if not isinstance(day, int):
        raise ValueError('bad day')
    
    if year < 1:
        raise ValueError('bad year')
    if month < 1 or month > 12:
        raise ValueError('bad month')
    if day < 1:
        raise ValueError('bad day')

    # Check for leap year
    is_leap_year = (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)

    # Days in each month, with February adjusted for leap years
    days_in_month = [31, 28 + int(is_leap_year), 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

    # Validate the day for the given month
    if day > days_in_month[month - 1]:
        raise ValueError('bad day')

    return sum(days_in_month[:month - 1]) + day
