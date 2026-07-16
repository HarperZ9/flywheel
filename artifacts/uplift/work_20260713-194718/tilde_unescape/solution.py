def untilde(s: str) -> str:
    def decode_char():
        if s.startswith("~n"):
            return "\n"
        elif s.startswith("~t"):
            return "\t"
        elif s.startswith("~x") and len(s) >= 3 and all(c in "0123456789abcdefABCDEF" for c in s[2:]):
            hex_val = int(s[2:], base=16)
            return chr(hex_val)
        else:
            raise ValueError("bad escape")
    
    result = []
    i = 0
    while i < len(s):
        if s[i:i+2] == "~n":
            result.append("\n")
            i += 2
        elif s[i:i+2] == "~t":
            result.append("\t")
            i += 2
        elif s[i:i+2] == "~x":
            hex_val = decode_char()
            result.append(hex_val)
            i += len(hex_val)
        else:
            result.append(s[i])
            i += 1
    if s.endswith('~'):
        raise ValueError("dangling escape")
    
    return ''.join(result)
