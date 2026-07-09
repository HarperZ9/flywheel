def valid_ipv4(s):
    parts = s.split('.')
    if len(parts) != 4:
        return False
    for p in parts:
        if not p.isdigit():
            return False
        if len(p) > 1 and p[0] == '0':
            return False
        if int(p) > 255:
            return False
    return True
