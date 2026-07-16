def parse_money(s):
    if s.strip() == '':
        raise ValueError('bad amount')
    
    # Remove leading '-' and trailing whitespace
    s = s.lstrip('- ')
    parts = s.split('.')
    
    if len(parts) > 2:
        raise ValueError('bad amount')
    
    integer_part = ''
    for part in parts[0].split(','):
        integer_part += part
    
    if len(parts) == 2 and (len(parts[1]) != 2 or not parts[1].isdigit()):
        raise ValueError('bad amount')
    
    decimal_part = int('.' + parts[1]) if len(parts) == 2 else 0
    
    return int(integer_part + str(decimal_part)) * -1 if s.startswith('-') else int(integer_part) * -1 if s.startswith('-') else int(integer_part)
