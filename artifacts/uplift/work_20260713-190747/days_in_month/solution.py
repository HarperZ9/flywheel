def days_in_month(year, month):
    if not isinstance(year, int) or bool(year):
        raise ValueError('bad year')
    if not isinstance(month, int) or bool(month) or not (1 <= month <= 12):
        raise ValueError('bad month')
    
    if month in [4, 6, 9, 11]:
        return 30
    elif month == 2:
        if year % 400 == 0 or (year % 100 != 0 and year % 4 == 0):
            return 29
        else:
            return 28
    else:
        return 31
