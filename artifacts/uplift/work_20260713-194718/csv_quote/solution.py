def csv_quote(field):
    if not isinstance(field, str):
        raise ValueError('bad field')
    
    bad_chars = [',', '"', '\r', '\n']
    quote_needed = any(char in field for char in bad_chars)
    
    if not quote_needed:
        return field

    # Double the double quotes within the field
    quoted_field = f'"{field.replace("\\", "\\\\").replace("\"", "\\\"")}"'
    
    return quoted_field
