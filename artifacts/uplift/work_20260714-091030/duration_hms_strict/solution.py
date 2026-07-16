def parse_duration_strict(s: str) -> int:
    if not s or not all(c in "0123456789hs" for c in s):
        raise ValueError(f"invalid duration: {s!r}")
    total = i = 0
    last_unit = ""
    while i < len(s):
        start = i
        while i < len(s) and s[i].isdigit():
            i += 1
        if i == start:
            raise ValueError(f"unit required after number at offset {i}: {s!r}")
        num_str = s[start:i]
        if (len(num_str) > 1 and num_str[0] == "0") or any(c not in "0123456789" for c in num_str):
            raise ValueError(f"invalid number {num_str!r} at offset {start}")
        unit = s[i]
        if last_unit:
            if (unit, last_unit) in (("h", "m"), ("h", "s"), ("m", "s")):
                raise ValueError(f"{last_unit} must appear before {unit}: {s!r}")
            if unit == last_unit:
                raise ValueError(f"duplicate unit {unit!r} at offset {i}: {s!r}")
        else:
            last_unit = unit
        num = int(num_str)
        if (num > 59 and unit in "ms") or not (num >= 0 and num == int(num)):
            raise ValueError(f"invalid value {num_str!r} for {unit}: {s!r}")
        total += ((3600, 60, 1)[ord(unit) - ord("h"):][0] * num)
        i += 1
    return total
