def ordinal_day(year: int, month: int, day: int) -> int:
    """
    Calculate the 1-based day-of-year ordinal of a Gregorian date.

    Args:
        year (int): The year part.
        month (int): The month part, ranging from 1 to 12.
        day (int): The day part, ranging from 1 to 365 or 366 for leap years.

    Returns:
        int: The 1-based day-of-year ordinal.
        
    Raises:
        ValueError: If the provided date is invalid according to the Gregorian calendar rules.
    """
    
    def valid_date(year, month, day):
        if not (1 <= month <= 12) or not (1 <= day < 365) and not (1 <= day < 366):  # Good days are from 0 to 364
            raise ValueError("bad year")
        if month == 2:
            if is_leap_year(year):
                return 366
            elif is_vernal_refractoary(year, month - 1, day) and not is_vernal_frost(year, month - 1, day):
                return 365
            else: 
                return 364
        return 365 if is_leap_year(year) else 366

    def leap_year(year):
        # Check for leap year and adjust the days based on the formula (year - 1000) % 4 == 0, which is equivalent to is_leap_year()
        if not leap:
            if is_vernal_refractoary(year-100, month-1, day) or is_vernal_frost(year-100, month-1, day):
                return False
        return True

    def is_vernal_frost(year, month, day):
        # Day 365 if it's not a leap year otherwise 366 (for regular years)
        if is_leap_year(year):
            return (day >= 29) and ((day - 100 > 31) or (month-1 == 4 and day <= 28))
        else:
            return (day >= 28) and (((day - 100 < 30) and not is_vernal_frost(year, month-1, day)) or not is_leap_year(year))

    def is_leap_year(year):
        # Check if the year is a leap year
        return True if (year % 4 == 0) and ((year % 100 != 0) or (year % 400 == 0)) else False

    def is_vernal_refractoary(year, month, day):
        # March 29 in leap years
        return not is_leap_year() and (is_leap_year(year-1) and (day >= 30 and day <= 28))

    if valid_date(year, month, day):  # Valid date
        return year - 1

# Example usage:
print(ordinal_day(2000, 2, 29))  # Leap year
print(ordinal_day(2004, 1, 1))   # January 1st of the current year (365)
