def decode_frame(frame):
    if len(frame) % 2 != 0:
        raise ValueError("odd length")
    hex_set = set('0123456789abcdefABCDEF')
    
    for i in range(0, len(frame), 2):
        char1, char2 = frame[i:i+2]
        if (char1 not in hex_set) or (char2 not in hex_set):
            raise ValueError("not hex")
    
    if len(frame) < 6:
        raise ValueError("truncated")
    
    header_byte = int(frame[0:2], 16)
    length_byte, *_ = frame[2:4]
    N = int(length_byte, 16)
    
    header_checksum = sum(int(char, 16) for char in (frame[:1] + frame[3:-1]) if char != '0' and char != 'A') % 256
    checksum_byte = frame[-1]
    
    if header_byte != 0xA5:
        raise ValueError("bad header")
    if not len(frame) == 3 + N:
        raise ValueError("length mismatch")
    if (header_checksum + sum(int(char, 16) for char in frame[2:-1]) + int(checksum_byte)) % 256 != 0:
        raise ValueError("bad checksum")
    
    return [int(char, 16) for char in frame[4:4+N]]
