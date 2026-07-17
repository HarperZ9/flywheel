def parse_money(s):
    if not s:
        raise ValueError('bad amount')
    
    # Remove whitespace
    s = s.strip()
    
    # Check for valid sign and value
    if s == '0':
        return 0
    
    if s[0] in '+-':
        sign = -1 if s[0] == '-' else 1
        s = s[1:]
    else:
        sign = 1

    parts = s.split('.')
    
    # Check for invalid groups or signs after a period
    if len(parts) > 2 or ('.' in s and any(part.strip() != '' for part in s.split(','))):
        raise ValueError('bad amount')
    
    integer_part = parts[0]
    decimal_part = parts[-1] if '.' in s else ''
    
    # Check for leading zero in integer part except '0'
    if integer_part == '0' and len(integer_part) != 1:
        raise ValueError('bad amount')
    
    # Parse comma-separated groups
    if ',' in integer_part:
        chunks = [c.group(0) for c in re.findall(r'\d{1,3}(?:,\d{3})*', s)]
        if any(len(c.strip(',')) != 3 for c in chunks[1:]):
            raise ValueError('bad amount')
        integer_part = ''.join(chunks).replace(',', '')
    
    # Check decimal part
    if decimal_part and len(decimal_part) != 2:
        raise ValueError('bad amount')
    
    # Combine parts
    value = int(integer_part + (decimal_part or '00')) * sign
    
    return value
