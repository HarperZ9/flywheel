def csv_quote(field: str) -> str:
    if not isinstance(field, str):
        raise ValueError('bad field')
    
    forbidden_chars = [',', '"', '\r', '\n']
    quote_needed = any(char in field for char in forbidden_chars)
    
    if quote_needed:
        # Double every double-quote inside the field and add quotes at start and end
        quoted_field = f'"{field.replace("\\\"", '\"')}"'
    else:
        # Return the field as-is, ensuring no surrounding quotes are added
        quoted_field = field
    
    return quoted_field
