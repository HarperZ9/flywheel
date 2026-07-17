def decode_frame(frame):
    if len(frame) % 2 != 0:
        raise ValueError("odd length")
    
    try:
        frame_bytes = bytes.fromhex(frame)
    except ValueError:
        raise ValueError("not hex")
    
    if len(frame_bytes) < 6:
        raise ValueError("truncated")
    
    header, length = frame_bytes[0], frame_bytes[1]
    if header != 0xA5:
        raise ValueError("bad header")
    
    payload_length = int(length)
    if len(frame_bytes) != 3 + payload_length:
        raise ValueError("length mismatch")
    
    payload_sum = sum(frame_bytes[2:2+payload_length])
    checksum = frame_bytes[-1]
    if (header + payload_sum + checksum) % 256 != 0:
        raise ValueError("bad checksum")
    
    return list(frame_bytes[2:2+payload_length].hex().encode().decode('hex'))
