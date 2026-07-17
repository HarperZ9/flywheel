def fletcher16(data):
    if not isinstance(data, (str, list)):
        raise ValueError('bad input')
    
    if isinstance(data, str):
        if any(ord(c) > 127 for c in data):
            raise ValueError('bad char')
        data = [ord(c) for c in data]
    
    sums = [0, 0]
    for byte in data:
        sums[0] = (sums[0] + byte) % 255
        sums[1] = (sums[1] + sums[0]) % 255
    
    return sums[1] * 256 + sums[0]
def fletcher16(data):
    if not isinstance(data, (str, list)):
        raise ValueError('bad input')
    
    if isinstance(data, str):
        if any(ord(c) > 127 for c in data):
            raise ValueError('bad char')
        data = [ord(c) for c in data]
    
    sums = [0, 0]
    for byte in data:
        sums[0] = (sums[0] + byte) % 255
        sums[1] = (sums[1] + sums[0]) % 255
    
    return sums[1] * 256 + sums[0]
