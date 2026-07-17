def decode_varints(data):
    def zigzag_decode(val):
        return val // 2 if val % 2 == 0 else -(val + 1) // 2

    out = []
    i = 0
    
    while i < len(data):
        j = i
        while True:
            if data[j] & 0x80 != 0:  # Continuation bit is set
                if j - i > 4 and ((j == len(data) - 1) or data[j+1] & 0x80 == 0):  # Check for overlong encoding
                    raise ValueError('overlong')
                break
            else:
                if j - i == 3:  # Truncated varint
                    raise ValueError("truncated")
                out.append(zigzag_decode(data[i] | data[i+1] << 8 | data[i+2] << 16 | data[i+3] << 24))
                i += 4
                break
        if j != i:
            out.append(zigzag_decode(data[i] | data[i+1] << 8 | data[i+2] << 16 | data[i+3] << 24))
            i += 4
        
        # Check for too long varint
        if (j - i) > 4 and ((j == len(data) - 1 or data[j+1] & 0x80 == 0):  # Last byte has continuation bit set
            raise ValueError("too long")
        
    return out
