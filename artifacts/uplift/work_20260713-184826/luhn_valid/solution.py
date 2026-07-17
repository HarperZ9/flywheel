def luhn_valid(s):
    if not isinstance(s, str) or len(s) == 0:
        raise ValueError('bad number')
    if not s.isdigit():
        raise ValueError('bad number')

    digits = [int(d) for d in s]
    checksum = sum(digits[-1::-2]) + sum(sum(divmod(2 * d, 10)) for d in digits[-2::-2])
    return checksum % 10 == 0
