def parse_range_list(s: str) -> list[int]:
    s = s.strip()
    if not s:
        return []
    out: set[int] = set()
    for part in s.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            try:
                lo, hi = int(a), int(b)
            except ValueError as exc:
                raise ValueError(f"malformed range {part!r}") from exc
            if lo > hi:
                raise ValueError(f"range {lo}-{hi} runs low-to-high")
            out.update(range(lo, hi + 1))
        else:
            try:
                n = int(part)
            except ValueError as exc:
                raise ValueError(f"malformed token {part!r}") from exc
            out.add(n)
    return sorted(out)
