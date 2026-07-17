def add_months(year, month, day, n):
    if not all(isinstance(i, int) for i in [year, month, day, n]) or isinstance(n, bool) or any(isinstance(i, bool) for i in [year, month, day]):
        raise ValueError("All arguments must be integers.")
    
    if year < 1 or month < 1 or month > 12 or day < 1:
        raise ValueError("Invalid date: year >= 1, 1 <= month <= 12, and 1 <= day <= number of days in that month of that year.")
    
    # Leap year rule
    def is_leap_year(y):
        return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)
    
    # Number of days in each month for a non-leap year
    days_in_month = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    
    # Adjust for leap years
    if is_leap_year(year):
        days_in_month[1] = 29
    
    month += n
    while month <= 0:
        year -= 1
        month += 12
        if is_leap_year(year):
            days_in_month[1] = 29
        else:
            days_in_month[1] = 28
    
    remaining_months = month % 12
    final_year = year + month // 12
    
    # Clamp day to the last day of the target month
    if day > days_in_month[remaining_months - 1]:
        day = days_in_month[remaining_months - 1]
    
    return (final_year, remaining_months, day)
