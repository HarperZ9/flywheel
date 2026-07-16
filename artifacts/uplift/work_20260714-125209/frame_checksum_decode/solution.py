def decode_frame(frame):
    frame = frame.lower()
    if len(frame) % 2 != 0:
        raise ValueError("odd length")
    if any(c not in "0123456789abcdef" for c in frame):
        raise ValueError("not hex")
    if len(frame) < 6:
        raise ValueError("truncated")

    bytes_ = [int(frame[i:i+2], 16) for i in range(0, len(frame), 2)]
    header, N = bytes_[0], bytes_[1]
    payload = bytes_[2:2+N]

    if header != 0xa5:
        raise ValueError("bad header")
    if len(bytes_) != 3 + N:
        raise ValueError("length mismatch")
    if sum(bytes_) % 256 != 0:
        raise ValueError("bad checksum")

    return payload
