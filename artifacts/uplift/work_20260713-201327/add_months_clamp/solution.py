from datetime import datetime

def add_months(year, month, day, n):
    """
    Adds n calendar months to a proleptic Gregorian date.
    Args:
        year (int): The year of the input date.
        month (int): The original month of the input date. Must be 1 <= month <= 12.
        day (int): The original day of the input date.
        n (int): The number of months to add. If n is negative, the function should not return
            or perform any changes. For example, if n=30, it will add 30 calendar months.

    Returns:
        tuple: A tuple containing the resulting year, month, and day.
        If adding n months would result in a date that appears in the past,
            an error message is returned instead of raising.
    """
    target_date = datetime(year, month, day)
    if n < 0:
        return 'Invalid number of months to add'
    
    current_year = target_date.year
    current_month = target_date.month - n  # Adjust month for negative n
    
    while True:
        new_target_date = datetime(current_year, current_month, 1) + \
            datetime(year, current_month, 1) - datetime(year, current_month, 1)
        
        if is_leap_year(current_year):
            new_target_date += datetime(year, 4, 0, 12, 31, 365)
            # Leap years end on the last day of February (in this case, 365 days)
            break

        if current_month in [1, 3, 5, 7, 8, 10, 12]:
            new_target_date += datetime(year, month + 9, 1) - datetime(year, month, 1)
        else:
            new_target_date += datetime(year, month, 1) - datetime(year, month, 1)

        if new_target_date > datetime(year, current_month, 4):
            n -= 1  # Add month back
            break
        
    return (current_year, new_target_date.month, new_target_date.day), 'Valid result'
    
def is_leap_year(year):
    """
    Check if a given year is a leap year.
    Args:
        year (int): The year to check.

    Returns:
        bool: True if the year is a leap year, False otherwise.
    """
    return (year % 4 == 0) and ((year % 100 != 0) or (year % 400 == 0))

# Example usage
if __name__ == "__main__":
    # Adding n months to a proleptic Gregorian date
    result = add_months(2023, 5, 7, -9)
    print(result)

    # Handling negative years and n greater than the month length
    try:
        add_months(-1, 5, 7, 100)
    except ValueError as e:
        print(e)  # Output: 'Invalid number of months to add'
