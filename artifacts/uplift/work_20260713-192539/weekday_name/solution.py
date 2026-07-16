def weekday_name(year: int, month: int, day: int) -> str:
    import datetime

    if not isinstance(year, int):
        raise ValueError("'year' should be an integer, not a boolean.")
    if not 1 <= year < 3000:
        raise ValueError("year must be at least 1 and no more than 2999.")

    if not isinstance(month, int):
        raise ValueError("'month' should be an integer, not a boolean.")
    if not 1 <= month <= 12:
        raise ValueError("month must be in the range of 1 to 12.")

    if not isinstance(day, int):
        raise ValueError("'day' should be an integer, not a boolean.")
    
    # Check if date is valid using datetime
    try:
        date = datetime.date(year, month, day)
    except ValueError as e:
        raise ValueError(f"bad day: {e}")

    days_of_week = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    weekday_index = (date.weekday() + 1) % 7
    return days_of_week[weekday_index]
