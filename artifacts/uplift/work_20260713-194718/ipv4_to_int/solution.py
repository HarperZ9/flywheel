def ipv4_to_int(s: str) -> int:
    if not isinstance(s, str):
        raise ValueError('bad address')
    
    parts = s.split('.')
    if len(parts) != 4:
        raise ValueError('bad address')

    for part in parts:
        if not part or not part.isdigit():
            raise ValueError('bad address')
        
        num = int(part)
        if num < 0 or num > 255:
            raise ValueError('bad address')
    
    return (int(parts[0]) << 24) | (int(parts[1]) << 16) | (int(parts[2]) << 8) | int(parts[3])
