def untilde(s):
    def hex_escape(match):
        return chr(int(match[0], 16))

    for i, char in enumerate(s, 0):
        if char == '~':
            s = s[:i-2] + hex_escape(s[i:i+2]) + ~s[i+3:]
            break

    return s
