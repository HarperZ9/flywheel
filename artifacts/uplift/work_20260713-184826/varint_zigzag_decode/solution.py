def decode_varints(data):
    if not all(isinstance(b, int) and 0 <= b <= 255 for b in data):
        raise ValueError("bad byte")

    def varint_to_signed_int(byte_list):
        n = 0
        for i, b in enumerate(byte_list):
            n |= (b & 0x7F) << (i * 7)
            if not b & 0x80:
                break
        else:
            raise ValueError("truncated")
        if n < (1 << 31):
            return n
        else:
            return -(1 << 31) - n

    result = []
    i = 0
    while i < len(data):
        try:
            varint = [data[i]]
            i += 1
            while data[i-1] & 0x80:
                varint.append(data[i])
                i += 1
            if len(varint) > 5:
                raise ValueError("too long")
            elif len(varint) >= 2 and not (varint[-1] & 0x7F):
                raise ValueError("overlong")
        except IndexError:
            raise ValueError("truncated")
        result.append(varint_to_signed_int(varint))
    return result
