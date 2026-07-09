def decode_varints(data):
    for b in data:
        if isinstance(b, bool) or not isinstance(b, int) or b < 0 or b > 255:
            raise ValueError("bad byte")
    out = []
    i = 0
    n = len(data)
    while i < n:
        u = 0
        shift = 0
        count = 0
        last = 0
        while True:
            if count == 5:
                raise ValueError("too long")
            if i >= n:
                raise ValueError("truncated")
            b = data[i]
            i += 1
            count += 1
            u |= (b & 0x7F) << shift
            shift += 7
            last = b
            if b & 0x80 == 0:
                break
        if count > 1 and last == 0:
            raise ValueError("overlong")
        out.append((u >> 1) ^ -(u & 1))
    return out
