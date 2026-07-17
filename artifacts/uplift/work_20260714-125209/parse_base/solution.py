def from_base(s: str, base: int) -> int:
    if isinstance(base, bool):
        raise ValueError('bad base')
    if not (2 <= base <= 36):
        raise ValueError('bad base')

    s = s.strip()
    if not s or s == '-':
        raise ValueError('bad digits')

    negate = False
    if s[0] == '-':
        negate = True
        s = s[1:]

    value = 0
    for char in s:
        if '0' <= char <= '9':
            digit_value = ord(char) - ord('0')
        elif 'a' <= char.lower() <= 'z':
            digit_value = ord(char.lower()) - ord('a') + 10
        else:
            raise ValueError('bad digits')

        if digit_value >= base:
            raise ValueError('bad digits')

        value = value * base + digit_value

    return -value if negate else value
