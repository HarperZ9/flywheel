def to_base(n, base):
    if not isinstance(base, int) or isinstance(base, bool):
        raise ValueError('bad base')
    if not 2 <= base <= 36:
        raise ValueError('bad base')
    if not isinstance(n, int) or isinstance(n, bool):
        raise ValueError('bad number')

    digits = '0123456789abcdefghijklmnopqrstuvwxyz'
    result = []

    n = abs(n)
    if n == 0:
        return '0'

    while n > 0:
        n, remainder = divmod(n, base)
        result.append(digits[remainder])

    if n < 0:
        result.append('-')

    return ''.join(result[::-1])
