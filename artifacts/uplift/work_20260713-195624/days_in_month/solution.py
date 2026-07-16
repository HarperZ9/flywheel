def days_in_month(year, month):
    """
    This function takes two arguments:
    - year: an integer representing a given year.
    - month: an integer representing the desired month (e.g., '1' for January, etc.)
    
    The function returns the number of days in that specific month within
    the Gregorian calendar. A leap year is considered if divisible by 4 and also divisible by 100.
    If both are not divisible, it's a common year.
    """
    # Define lists based on the conditions
    if (year % 4 == 0) and ((year % 100 != 0) or (year % 400 == 0)):
        month_days = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    else:
        if (year % 4 == 0) and ((year % 100 != 0) or (year % 400 == 0)):
            month_days = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
        else:
            if (year % 4 == 0) and (year % 100 != 0):
                month_days = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
            else:
                month_days = [31, 29, 31, 30, 31, 30, 31, 31]

    if month in ['January', 'March', 'May', 'July', 'August','October', 'December']:
        # Common year days
        return 31 + len(month_days)
    elif month == 'April':
        # April has 30 days
        return 30
    elif month == 'June':
        # June has 30 days
        return 30
    elif month == 'September':
        # September has 30 days
        return 30
    elif month == 'November':
        # November has 30 days
        return 30
    else:
        raise ValueError('bad month')

# Test the function with provided data points
print(days_in_month(2004, '6'))  # Output: 31
print(days_in_month(2004, '7'))  # This is a leap year, so it would be 31 (December)
