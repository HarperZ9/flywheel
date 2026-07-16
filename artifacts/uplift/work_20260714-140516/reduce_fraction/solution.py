from math import gcd


def reduce_fraction(num: int, den: int) -> tuple[int, int]:
    if not isinstance(num, int) or not isinstance(den, int):
        raise ValueError("bad arg")
    if not den:
        raise ValueError("div by zero")
    g = abs(gcd(num, den))
    return (num // g) * (-1 if den < 0 else 1), abs(den) // g
