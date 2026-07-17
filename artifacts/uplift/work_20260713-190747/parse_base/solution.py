def from_base(s, base):
    if not isinstance(base, int) or isinstance(base, bool):
        raise ValueError('bad base')
    if not 2 <= base <= 36:
        raise ValueError('bad base')

    s = s.strip()
    if not s or s == '-':
        raise ValueError('bad digits')

    sign = -1 if s[0] == '-' else 1
    if s[0] in '-+':
        s = s[1:]

    digit_map = {char: idx for idx, char in enumerate('0123456789abcdefghijklmnopqrstuvwxyz')}
    value = 0

    for char in s.lower():
        if char not in digit_map or digit_map[char] >= base:
            raise ValueError('bad digits')
        value = value * base + digit_map[char]

    return sign * value
