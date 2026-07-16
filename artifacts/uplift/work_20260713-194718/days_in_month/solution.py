def days_in_month(year: int, month: int) -> int:
    if not isinstance(year, int) or not isinstance(month, int):
        raise ValueError('bad year')
    if bool(year) != year:
        raise ValueError('bad year')
    if month < 1 or month > 12:
        raise ValueError('bad month')

    # Check for leap years
    is_leap = (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0))
    
    # Days in months
    if month == 2:  # February
        return 29 if is_leap else 28
    elif month in [4, 6, 9, 11]:  # April, June, September, November
        return 30
    else:
        return 31
