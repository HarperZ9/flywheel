def weekday_name(year: int, month: int, day: int) -> str:
    """
    Returns the English weekday name for a proleptic Gregorian date.
    
    Args:
        year (int): The year of the date.
        month (int): The month of the date.
        day (int): The day of the date.
        
    Raises:
        ValueError: If the year, month, or day are out of range or if any other problem occurs.
    """
    
    # Check if the year, month, and day values are valid
    if not isinstance(year, int) or not (1 <= year <= 31):
        raise ValueError(f'year is not an integer or in range [1, 31]')
    if not isinstance(month, int) or not (1 <= month <= 12):
        raise ValueError(f'month is not an integer or in range [1, 12]')
    if not year > 0:
        raise ValueError('year must be a positive integer')
    
    # Check the day
    days = [
        'day', 
        'Sunday', 
        'Monday',
        'Tuesday',
        'Wednesday',
        'Thursday',
        'Friday'
    ]
    
    if month == 2 and (isinstance(year, int) and year % 400 == 0 or (year % 100 != 0 and year % 4 == 0)):
        days[5] = "Tuesday"
    elif not day:
        raise ValueError('day must be a non-negative integer')
    
    # Return the weekday name
    return days[day]
try:
    print(weekday_name(year=2019, month=1, day=1))  # Tuesday
    print(weekday_name(year=2019, month=4, day=25))  # No leap year, so it's a Sunday
    print(weekday_name(year=1911, month=3, day=25))  # Friday (March 3rd)
    print(weekday_name(month=3, year=2016))  # Wednesday (March 30th)
except ValueError as e:
    print(e)
