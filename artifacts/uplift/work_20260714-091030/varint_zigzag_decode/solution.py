def decode_varints(data):
    for b in data:
        if not isinstance(b, int) or not (0 <= b <= 255):
            raise ValueError("bad byte")
        
    result = []
    i = 0
    while i < len(data):
        value = 0
        shift = 0
        
        # Process up to 4 continuation bytes
        for _ in range(4):
            if data[i] & 0x80:
                if shift == 28:  # would overflow a signed 32-bit int
                    raise ValueError("too long")
                value |= (data[i] & 0x7F) << shift
                i += 1
                shift += 7
            else:
                break
        
        # Check if we reached the end of data too early
        if i == len(data):
            if data[-1] & 0x80:
                raise ValueError("truncated")
            value |= (data[i - 1] & 0x7F) << shift
        
        # Apply ZigZag decode
        result.append((value >> 1) ^ -(value & 1))
    
    return result
