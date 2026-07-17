def parse_money(s):
    if not s.strip():
        return 0

    # Remove any whitespace and validate the format using a regular expression
    s = s.strip()
    import re
    match = re.fullmatch(r'(-)?\d{1,3}(,\d{3})*(\.\d{2})?', s)
    
    if not match:
        raise ValueError('bad amount')
    
    # Extract matched groups
    sign, integer_part, decimal_part = match.groups()
    
    # Convert to integer value of cents
    integer_value = int(integer_part.replace(',', ''))
    if decimal_part is None:
        return integer_value * 100
    else:
        tens, units = map(int, decimal_part)
        return integer_value * 100 + (tens * 10 + units) * 10
