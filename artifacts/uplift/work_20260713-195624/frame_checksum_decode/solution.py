def decode_frame(frame):
    """
    Validates and decodes a hex-encoded protocol frame.
    
    Args:
        frame: A string representing a valid frame encoded in HEX.

    Returns:
        int_list: The payload bytes as a list of integers.
    """
    header_hex = frame[:3]  # First byte (header) is always '0xA5'
    length_hex = frame[4]   # Second byte + checksum for total length

    # Validate that the frame has exactly 6 characters and no non-hex and odd-length bytes
    if len(frame) != 6 or not all(c in '0123456789abcdefABCDEF' for c in frame):
        raise ValueError("bad length")
    
    total_length = int(length_hex, 16)
    payload = []
    checksum = header_hex + (total_length - (len(frame) % 256)) if len(frame) % 256 else header_hex
    n_bytes = len(frame) // 4

    for i in range(n_bytes):
        byte_sum = (int(frame[i*4:i*4+1]) << 8) + int(frame[i*4+1:i*4+2])
        payload.append(byte_sum & 0xFF)

    if total_length % 256:  # Check if the frame is truncated
        raise ValueError("truncated")
    
    return list(payload)

# Test cases to verify the correctness of the solution
if __name__ == "__main__":
    test_cases = [
        "A5B108C4",
        "0x54",
        "",
        "Invalid Hex: 9aAB"
    ]

    for frame in test_cases:
        try:
            payload = decode_frame(frame)
            print(f"Frame '{frame}' is valid with payload {payload}")
        except ValueError as e:
            print(f"Frame '{frame}' raises ValueError: {e}")
