def ipv4_to_int(s: str) -> int:
    if not isinstance(s, str):
        raise ValueError('bad address')
    
    parts = s.split('.')
    if len(parts) != 4:
        raise ValueError('bad address')

    for part in parts:
        if not part.isdigit() or (len(part) > 1 and part[0] == '0') or int(part) < 0 or int(part) > 255:
            raise ValueError('bad address')
    
    return (
        int(parts[0]) << 24 |
        int(parts[1]) << 16 |
        int(parts[2]) << 8  |
        int(parts[3])
    )
