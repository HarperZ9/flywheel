from datetime import date

def days_between(d1, d2):
    if len(d1) != 3 or len(d2) != 3:
        raise ValueError('bad date')
    
    year1, month1, day1 = d1
    year2, month2, day2 = d2
    
    if not (year1 >= 1 and 1 <= month1 <= 12 and 1 <= day1 <= _days_in_month((year1, month1))):
        raise ValueError('bad date')
    
    if not (year2 >= 1 and 1 <= month2 <= 12 and 1 <= day2 <= _days_in_month((year2, month2))):
        raise ValueError('bad date')
    
    d1_date = date(year1, month1, day1)
    d2_date = date(year2, month2, day2)
    
    return int(d2_date - d1_date)

def _days_in_month(date):
    if date[1] == 2:  # February
        return 29 if (date[0] % 4 == 0 and (date[0] % 100 != 0 or date[0] % 400 == 0)) else 28
    elif date[1] in [4, 6, 9, 11]:  # April, June, September, November
        return 30
    else:  # All other months
        return 31
