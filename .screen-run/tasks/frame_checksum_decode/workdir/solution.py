def decode_frame(frame):
    if len(frame) % 2 != 0:
        raise ValueError("odd length")
    hexdigits = set("0123456789abcdefABCDEF")
    if any(c not in hexdigits for c in frame):
        raise ValueError("not hex")
    if len(frame) < 6:
        raise ValueError("truncated")
    data = [int(frame[i:i + 2], 16) for i in range(0, len(frame), 2)]
    if data[0] != 0xA5:
        raise ValueError("bad header")
    n = data[1]
    if len(data) != 3 + n:
        raise ValueError("length mismatch")
    payload = data[2:2 + n]
    if (data[0] + n + sum(payload) + data[-1]) % 256 != 0:
        raise ValueError("bad checksum")
    return payload
