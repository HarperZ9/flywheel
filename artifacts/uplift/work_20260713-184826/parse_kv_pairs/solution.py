def parse_kv(s):
    if not isinstance(s, str):
        raise ValueError('bad input')
    
    result = []
    seen_keys = set()
    
    items = s.split(';')
    
    for item in items:
        if item == '':
            continue
        
        key_value = item.split('=')
        
        if len(key_value) != 2:
            raise ValueError('bad item')
        
        key, value = key_value
        
        if not key or not key.isidentifier():
            raise ValueError('bad item')
        
        if '=' in value:
            raise ValueError('bad item')
        
        if key in seen_keys:
            raise ValueError('duplicate key')
        
        seen_keys.add(key)
        result.append((key, value))
    
    return result
