def parse_kv(s):
    """
    Parse a semicolon-separated list of key-value assignments into a list of (key, value) tuples.
    
    Parameters:
        s (str): A comma-separated list of key-value pairs, e.g., "name;age:42". 
    
    Returns:
        list of (key, value) tuples if the input is valid. Raises ValueError otherwise.
    
    Examples:
        >>> parse_kv("name;age:42")
        [('name', 'age:42')]
        
        >>> parse_kv("color:blue;size:7")
        [('color', 'blue'), ('size', '7')]
        
        >>> parse_kv("")
        []
        
        >>> parse_kv("color;same_name:same_value")
        ValueError('bad input.')
    """
    
    if not s:
        return []
    
    key, value = s.split(';')
    try:
        key = key.strip()
        value = value.strip()
        
        # Check for duplicate keys
        if len(key) > 0 and key in kv_map:
            raise ValueError(f"Duplicate key encountered: {key}")
        
        # Check for invalid keys or bad characters
        if not key.isalnum() and key != '_':
            raise ValueError("Invalid key character.")
        
        if '=' in value:
            raise ValueError("Value must have a single equals sign.")
    
    except (IndexError, ValueError) as e:
        raise ValueError(f"Invalid input: {e}")
    
    return [(key, value)]
