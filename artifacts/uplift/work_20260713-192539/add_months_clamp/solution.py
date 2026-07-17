def add_months(year: int, month: int, day: int, n: int) -> tuple:
    if not all(isinstance(arg, int) and arg > 0 for arg in [year, month, day, n]):
        raise ValueError("All arguments must be positive integers.")
    
    # Validate input date
    from datetime import timedelta
    date = timedelta(days=day - 1)
    valid_date = datetime(year, month, day + 1) - date
    
    if not (1 <= month <= 12 and 0 < day <= valid_date.day):
        raise ValueError("Invalid date. The year must be >= 1, the month must be between 1 and 12, "
                          "and the day must be between 1 and the day of that month.")
    
    # Add n months
    from calendar import monthrange
    
    total_days = (valid_date - timedelta(days=1)).days + n * monthrange(year, month)[1]
    new_month, new_day = divmod(total_days, 30)
    
    # Clamp down to valid day in the target month
    if new_day == 0:
        new_day = monthrange(year, new_month)[1]
        new_month -= 1
    
    if new_month < 1:
        year -= 1
        new_month += 12
    
    return (year, new_month, new_day)
