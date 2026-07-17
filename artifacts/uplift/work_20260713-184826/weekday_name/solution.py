def weekday_name(year, month, day):
    import calendar
    
    if not isinstance(year, int) or year < 1:
        raise ValueError('bad year')
    if not isinstance(month, int) or month < 1 or month > 12:
        raise ValueError('bad month')
    if not isinstance(day, int) or day < 1:
        raise ValueError('bad day')
    max_day = calendar.monthrange(year, month)[1]
    if day < 1 or day > max_day:
        raise ValueError('bad day')
    
    return ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'][calendar.weekday(year, month, day)]
