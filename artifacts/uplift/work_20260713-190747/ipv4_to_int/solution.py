def ipv4_to_int(s: str) -> int:
    parts = s.split('.')
    if len(parts) != 4:
        raise ValueError('bad address')
    
    for part in parts:
        if not part.isdigit() or (part.startswith('0') and len(part) > 1):
            raise ValueError('bad address')
        value = int(part)
        if value < 0 or value > 255:
            raise ValueError('bad address')
    
    return (int(parts[0]) << 24) + (int(parts[1]) << 16) + (int(parts[2]) << 8) + int(parts[3])
