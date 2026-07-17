def valid_ipv4(s: str) -> bool:
    parts = s.split('.')
    
    if len(parts) != 4:
        return False
    
    for part in parts:
        if not part.isdigit():
            return False
        
        if part == '0' or (part[0] != '0' and int(part) <= 255):
            continue
        else:
            return False
    
    return True
