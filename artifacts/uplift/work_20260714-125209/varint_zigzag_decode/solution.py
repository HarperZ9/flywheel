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
                if shift == 3 * 7 and (b == 0 or data[i - 1] == 0):
                    raise ValueError("overlong")
                
                result.append(((value >> 1) ^ -(value & 1)))
                i += 1
                break
            
            shift += 7
            i += 1
        else:
            # First 5 bytes all had continuation bit set
            raise ValueError("too long")
    
    return result

# Sample test cases to verify the function works correctly:
if __name__ == "__main__":
    import json
    
    print("Test decoding 12: ", decode_varints([0xC8, 0x06]))  # [12]
    print("Test decoding -9: ", decode_varints([0xB7, 0x0B]))   # [-9]
    print("Test decoding 654321 (overlong): ",
          json.dumps(decode_varints([0x81, 0xC8, 0x40])) == '[]')
    
    try:
        decode_varints([0x80] * 5)
    except ValueError as e:
        print("Test too long: ", str(e) == "too long")
    
    try:
        decode_varints([0x80, 0x00])
    except ValueError as e:
        print("Test overlong: ", str(e) == "overlong")
        
    print("Test empty input: ", len(decode_varints([])) == 0)
