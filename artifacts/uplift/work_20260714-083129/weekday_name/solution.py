def weekday_name(year, month, day):
    from datetime import date

    # Validate inputs
    if not isinstance(year, int):
        raise ValueError('year an int, not a bool, at least 1 -> "bad year"')
    if not (isinstance(month, int) and 1 <= month <= 12):
        raise ValueError('month an int, not a bool, in 1 through 12 -> "bad month"')
    if not (isinstance(day, int) and 1 <= day <= date(year, month, 1).days_in_month):
        raise ValueError('day an int, not a bool, at least 1 and at most the real length of that month in that year -> "bad day"')
    
    # Determine if it's a leap year
    is_leap = ((year % 4 == 0) and (not(year % 100 == 0)) or (year % 400 == 0))

    # Days in each month, accounting for February on leap years
    days_in_month = [31, 29 if is_leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    
    # Calculate day of week
    total_days = sum(days_in_month[:month-1]) + day - 1
    
    # Days of the week mapping, Monday is 0 in Python's datetime module
    days_of_week_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    
    return days_of_week_names[total_days % 7]
