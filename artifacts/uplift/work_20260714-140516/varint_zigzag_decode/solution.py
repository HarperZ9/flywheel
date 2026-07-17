def decode_varints(data):
    if not all(isinstance(b, int) and 0 <= b <= 255 for b in data):
        raise ValueError("bad byte")
    
    result = []
    i = 0
    
    while i < len(data):
        value = 0
        shift = 0
        
        for _ in range(5):  # maximum varint length is 5 bytes
            if i == len(data) and shift > 0:
                raise ValueError("truncated")
            
            b = data[i]
            value |= (b & 0x7F) << shift
            
            if not (b & 0x80):
                # Check for overlong encoding: second-to-last byte must be >= 64
                if shift == 3 * 7 and (b == 1 or b == 0):
                    raise ValueError("overlong")
            
                result.append((value // 2) if value % 2 == 0 else -((value + 1) // 2))
                
                i += 1
                break
            
            # First 5 bytes all with continuation bit: too long
            if shift == 0 and (b & 0x80) and data[i+1] & 0x80:
                raise ValueError("too long")
            
            shift += 7
            i += 1
        
        else:
            # Used up all 5 bytes but still have continuation bit set
            if data[i-4] & 0x80:
                raise ValueError("overlong")
    
    return result
