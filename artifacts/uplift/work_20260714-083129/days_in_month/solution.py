def days_in_month(year, month):
    if not isinstance(year, int) or isinstance(year, bool):
        raise ValueError('bad year')
    if not isinstance(month, int) or isinstance(month, bool):
        raise ValueError('bad month')
    if 1 <= month <= 12:
        if month == 2:  # February
            return 29 if is_leap_year(year) else 28
        elif month in [4, 6, 9, 11]:  # April, June, September, November
            return 30
        else:
            return 31
    else:
        raise ValueError('bad month')
        
def is_leap_year(year):
    if year % 4 != 0:
        return False
    elif year % 100 != 0:
        return True
    elif year % 400 == 0:
        return True
    else:
        return False
