def valid_ipv4(s):
    p = s.split(".")
    if len(p) != 4:
        return False
    for x in p:
        if not (x.isdigit() and str(int(x)) == x and 0 <= int(x) <= 255):
            return False
    return True
