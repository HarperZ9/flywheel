def parse_duration_strict(s):
    order = {'h': 0, 'm': 1, 's': 2}
    mult = {'h': 3600, 'm': 60, 's': 1}
    if s == "":
        raise ValueError("empty duration")
    i = 0
    n = len(s)
    last = -1
    total = 0
    first = True
    while i < n:
        j = i
        while j < n and '0' <= s[j] <= '9':
            j += 1
        if j == i:
            raise ValueError("expected digits")
        num = s[i:j]
        if len(num) > 1 and num[0] == '0':
            raise ValueError("leading zeros")
        if j >= n:
            raise ValueError("digits without a unit")
        unit = s[j]
        if unit not in order:
            raise ValueError("unknown unit")
        if order[unit] <= last:
            raise ValueError("unit out of order or duplicated")
        last = order[unit]
        val = int(num)
        if not first and unit in ('m', 's') and val > 59:
            raise ValueError("non-leading component out of range")
        total += val * mult[unit]
        first = False
        i = j + 1
    return total
