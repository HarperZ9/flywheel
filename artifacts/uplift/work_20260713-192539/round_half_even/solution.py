def round_half_even(num: int, den: int) -> int:
    if not isinstance(num, int) or not isinstance(den, int):
        raise ValueError('bad arg')
    if den == 0:
        raise ValueError('div by zero')

    result = num / den
    # Round the number to the nearest integer using round-half-to-even (banker's rounding)
    return int(round(result))
