def parse_a1(ref) -> tuple[int, int]:
    if not isinstance(ref, str):
        raise ValueError("bad ref")
    parts = [p for p in _A1_RE.split(ref) if p]
    if len(parts) != 2:
        raise ValueError("bad ref")
    letters, digits = parts
    if any(ord(c) > ord("Z") or not ("A" <= c) for c in letters):
        raise ValueError("bad ref")
    if not digits.isascii() or not digits.isdigit() or int(digits[0]) == 0:
        raise ValueError("bad ref")
    return int(digits), _BASE_26(letters)
