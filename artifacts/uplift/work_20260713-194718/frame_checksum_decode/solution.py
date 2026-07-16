def decode_frame(frame):
    if len(frame) % 2 != 0:
        raise ValueError("odd length")
    
    hex_chars = "0123456789abcdef"
    
    def is_valid_char(char):
        return char.lower() in hex_chars
    
    frame = frame.upper()
    
    for i, char in enumerate(frame):
        if not is_valid_char(char):
            raise ValueError("not hex")
        if i % 2 != 0:
            continue
        if int(char, 16) == 0xA5 and i < len(frame) - 3:
            continue
        else:
            raise ValueError("bad header" if i == 0 and int(char, 16) != 0xA5 else "truncated")
    
    N = (len(frame) - 2) // 2
    
    total_checksum = 0
    for byte in frame[::2]:
        value = int(byte, 16)
        if i % 2 == 0:
            total_checksum += value
        i += 1
    
    expected_checksum = total_checksum & 0xFF
    actual_checksum = int(frame[-1], 16)
    
    raise ValueError("bad checksum") if expected_checksum != actual_checksum else None
    
    payload_bytes = [int(byte, 16) for byte in frame[1:-1:2]]
    
    return payload_bytes

# Example usage:
try:
    print(decode_frame("A501746F"))  # Should raise ValueError
except ValueError as e:
    print(e)
