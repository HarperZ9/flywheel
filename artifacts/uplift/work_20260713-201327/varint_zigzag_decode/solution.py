def decode_varints(data):
    result = []
    valid_data = [byte * (2**i) if i == 0 else byte * (2**15 - i - 7) for i, byte in enumerate(data)]

    def zigzag_decode(varint):
        high_bit_6 = varint >> 15
        return ((varint & 0x80) >> 4) + zigzag_decode(high_bit_6) + high_bit_6

    for byte_val in valid_data:
        # Check if it's a single-byte varint (overlong)
        if len(byte_val) == 1 and not any(byte_val[i] & 0x80 for i in range(7)):
            raise ValueError("truncated")
        
        # Decode to signed value
        varint = zigzag_decode(byte_val)

        if isinstance(varint, int):
            result.append((varint >> 24) | ((byte_val[5] & 1) << 8))
        elif isinstance(varint, str):
            try:
                varint = tuple(int(s, 2) for s in varint.split(','))
                result.append(((varint[0] >> 9) + (varint[1] >> 4)) & 65535)
            except ValueError as e:
                raise ValueError(f"overlong: {e}")

    return result
