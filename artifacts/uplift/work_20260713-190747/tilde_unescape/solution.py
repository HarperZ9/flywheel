def untilde(s):
    if not s:
        return ""
    
    decoded = []
    i = 0
    
    while i < len(s):
        if s[i] == "~":
            if i + 1 == len(s):  # "~" as the last character with nothing after it
                raise ValueError("dangling escape")
            i += 1
            next_char = s[i]
            
            if next_char == "n":  # newline
                decoded.append("\n")
                i += 1
            elif next_char == "t":  # tab
                decoded.append("\t")
                i += 1
            elif next_char == "x":  # hex escape sequence
                if i + 2 > len(s):  # "~x" followed by fewer than two remaining characters
                    raise ValueError("bad hex")
                try:
                    hex_digit = s[i+1:i+3]
                    decoded.append(chr(int(hex_digit, 16)))
                    i += 3
                except ValueError:  # either of the next two characters is not a hex digit
                    raise ValueError("bad hex")
            else:  # "~" followed by any character other than "~", "n", "t", "x"
                raise ValueError("bad escape")
        else:
            if ord(s[i]) < 32 and s[i] not in "\r\n":  # literal (unescaped) character with code point < 32
                raise ValueError("raw control")
            decoded.append(s[i])
            i += 1
    
    return "".join(decoded)
