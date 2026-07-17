from __future__ import annotations


def _gcd(a: int, b: int) -> int:
    a = abs(a)
    b = abs(b)
    while b != 0:
        a, b = b, a % b
    return a


def reduce_fraction(num: object, den: object) -> tuple[int, int]:
    if not isinstance(num, int) or not isinstance(den, int):
        raise ValueError("bad arg")
    d = _gcd(num, den)
    num //= d
    den //= d
    if den < 0:
        num = -num
        den = -den
    return (num, den)
