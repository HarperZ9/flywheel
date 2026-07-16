def valid_ipv4(s):
    if not s or len(s) < 7 or len(s) > 15:
        return False

    parts = s.split('.')
    for part in parts:
        if not part.isdigit() or int(part) > 255 or (part.startswith('0') and len(part) > 1):
            return False
    return True
