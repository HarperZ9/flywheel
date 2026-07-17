def fletcher16(data):
    if isinstance(data, str):
        for c in data:
            if ord(c) > 127:
                raise ValueError('bad char')
        bytes_ = [ord(c) for c in data]
    elif isinstance(data, list):
        for b in data:
            if not isinstance(b, int) or isinstance(b, bool):
                raise ValueError('bad byte')
            if not (0 <= b <= 255):
                raise ValueError('bad byte')
        bytes_ = data
    else:
        raise ValueError('bad input')
    sum1 = sum2 = 0
    for b in bytes_:
        sum1 = (sum1 + b) % 255
        sum2 = (sum2 + sum1) % 255
    return (sum2 << 8) | sum1
