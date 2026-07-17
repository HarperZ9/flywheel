def parse_kv(s):
    if not s:
        return []
    
    items = s.split(';')
    seen_keys = set()
    result = []

    for item in items:
        parts = item.split('=')
        if len(parts) != 2:
            raise ValueError('bad item')
        
        key, value = parts
        if not (key and isinstance(key, str)):
            raise ValueError('bad item')
        if not (value and isinstance(value, str)):
            raise ValueError('bad item')

        if key in seen_keys:
            raise ValueError('duplicate key')
        seen_keys.add(key)
        
        if any(c.isdigit() or c == '_' for c in key):
            pass
        else:
            raise ValueError('bad key')
        
        result.append((key, value.strip()))
    
    return result
