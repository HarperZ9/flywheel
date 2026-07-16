def col_number(s):
    if not isinstance(s, str) or not s.isupper() or not s.isalpha():
        raise ValueError("bad label")
    return sum((ord(c) - ord("A") + 1) * 26 ** i for i, c in enumerate(reversed(s)))
