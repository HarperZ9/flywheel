def ordinal_day(year: int, month: int, day: int) -> int:
    if not isinstance(year, int) or year < 1:
        raise ValueError('bad year')
    
    if not isinstance(month, int) or month < 1 or month > 12:
        raise ValueError('bad month')
    
    # Check if the year is a leap year
    is_leap_year = (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0))
    
    # Days in each month for common years
    days_in_month = [31, 28 if not is_leap_year else 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    
    # Check if the day is valid given the month and whether it's a leap year
    if not isinstance(day, int) or day < 1 or day > days_in_month[month - 1]:
        raise ValueError('bad day')
    
    # Calculate the ordinal day of the year
    if month == 2:  # February
        return day + sum(days_in_month[:month-1])
    else:
        return day + sum(days_in_month[:month-1])
