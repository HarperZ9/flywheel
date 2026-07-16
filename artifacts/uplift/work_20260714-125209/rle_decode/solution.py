def rle_decode(s: str) -> str:
    out = []
    i = 0
    while i < len(s):
        j = i
        while j < len(s) and s[j].isdigit():
            j += 1
        if j == i or j == len(s):  # no digits / ends with a count
            raise ValueError(f"malformed at {i}: {s!r}")
        n = int(s[i:j])
        if n <= 0:
            raise ValueError(f"non-positive count {n} at {i}")
        out.append(s[j] * n)
        i = j + 1
    return "".join(out)
