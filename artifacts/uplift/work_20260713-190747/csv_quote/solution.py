def csv_quote(field):
    if not isinstance(field, str):
        raise ValueError('bad field')
    
    contains_special_chars = ',' in field or '\n' in field or '\"' in field
    
    if not contains_special_chars:
        return field
    
    quoted_field = f'"{field.replace(\"\", \"\\"\")}"'
    return quoted_field
