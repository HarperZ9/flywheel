def days_between(d1, d2):
    if not (isinstance(d1, tuple) and isinstance(d2, tuple)):
        raise ValueError('arguments must be tuples')
    
    if not all(isinstance(x, int) for x in d1 + d2):
        raise ValueError('all date components must be integers')
    
    if any(not isinstance(mo, int) or not (1 <= mo <= 12) for mo in d1 + d2):
        raise ValueError('months must be integers between 1 and 12')
    
    if not all(1 <= x <= 31 for x in d1 + d2):
        raise ValueError('days must be at least 1 and at most the real length of that month in that year')
    
    year, month, day = min(d1, d2)
    late_year, late_month, late_day = max(d1, d2)
    
    if (late_year - year) * 365 + ((late_year % 4 == 0 and not (late_year % 100 == 0)) or late_year % 400 == 0) > day - min(day, late_day):
        return (days_between((year, month, day), d2) if day < late_day else days_between(d1, late_day))
    
    if late_month != month:
        return (late_day - day + days_between((late_year, late_month, 1), d2)) if day <= late_day else -(days_between(d1, late_day - 1))
    
    if late_day < day:
        return days_between((year, month, max(day - late_day, 0)), (late_year, late_month, late_day - 1))
    
    return late_day - day
