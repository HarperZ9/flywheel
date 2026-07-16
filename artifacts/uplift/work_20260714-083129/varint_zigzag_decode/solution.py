def decode_varints(data):
    def zigzag_decode(v):
        return v // 2 if v % 2 == 0 else -(v + 1) // 2

    def varint_length(u):
        length = 1
        while (u >> 7) > 0:
            u <<= 1
            length += 1
        return length

    results = []
    
    for byte in data:
        if not isinstance(byte, int) or not 0 <= byte <= 255:
            raise ValueError("bad byte")
        
        varint_bytes = [byte]
        next_byte = True
        
        while next_byte:
            try:
                varint_bytes.append(data.index(next(data)))
                next_byte = False
            except ValueError:
                break

        if len(varint_bytes) == 1 or varint_length(varint_bytes[0]) != len(varint_bytes):
            raise ValueError("overlong")

        u = sum(b << (7 * i) for i, b in enumerate(reversed(varint_bytes)))
        
        try:
            results.append(zigzag_decode(u))
        except OverflowError:
            raise ValueError("too long") from None

    return results
