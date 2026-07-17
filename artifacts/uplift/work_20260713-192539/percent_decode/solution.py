def percent_decode(s: str) -> str:
    def decode_hex(hex_str: str) -> int:
        return int(hex_str, 16)
    
    i = 0
    while i < len(s):
        if s[i] == '%':
            if i + 2 >= len(s):
                raise ValueError('bad escape')
            
            hex_part = s[i+1:i+3]
            byte_value = decode_hex(hex_part)
            
            if byte_value > 127:
                raise ValueError('non-ascii byte')
                
            i += 3
        else:
            yield s[i]
            i += 1
