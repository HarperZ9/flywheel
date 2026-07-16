def parse_kv(s: str) -> list:
    if not s:
        return []
    
    items = s.split(';')
    result = []
    
    for i, kv in enumerate(items):
        parts = kv.split('=')
        
        if len(parts) != 2:
            raise ValueError('bad item')
            
        key, value = parts
        if not key.strip():
            raise ValueError('empty key')
        
        allowed_chars = 'abcdefghijklmnopqrstuvwxyz0123456789_'
        for char in key:
            if char not in allowed_chars:
                raise ValueError('bad key character')
                
        result.append((key, value))
    
    seen_keys = set()
    for i, (key, _) in enumerate(result):
        if key in seen_keys:
            raise ValueError('duplicate key')
        
        seen_keys.add(key)
        
    return result
