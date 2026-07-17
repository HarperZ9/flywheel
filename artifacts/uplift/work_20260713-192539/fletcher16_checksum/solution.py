def fletcher16(data):
    if isinstance(data, str):
        for char in data:
            if ord(char) > 127:
                raise ValueError('bad char')
        byte_sequence = bytes(data, 'ascii')
    elif isinstance(data, list):
        if all(isinstance(x, int) and not isinstance(x, bool) and 0 <= x <= 255 for x in data):
            byte_sequence = bytes(data)
        else:
            raise ValueError('bad byte')
    else:
        raise ValueError('bad input')

    checksum = [0, 0]
    for byte in byte_sequence:
        checksum[0] = (checksum[0] + byte) % 255
        checksum[1] = (checksum[1] + checksum[0]) % 255

    return checksum[1] * 256 + checksum[0]
