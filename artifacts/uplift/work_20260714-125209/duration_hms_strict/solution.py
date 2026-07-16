def parse_duration_strict(s: str) -> int:
    if not s or not all(c in "0123456789hms" for c in s):
        raise ValueError("invalid duration format")
    i = 0
    seen_h = False
    total = 0
    while i < len(s):
        if s[i] in "hms":
            unit = s[i]
            i += 1
            start = i
            while i < len(s) and s[i].isdigit():
                i += 1
            if start == i or not (s[start] == "0" or all(c != "0" for c in s[start])):
                raise ValueError("invalid number")
            numstr = s[start:i]
            n = int(numstr)
            if unit == 'h':
                if seen_h:
                    raise ValueError("duplicate hour component")
                total += n * 3600
                seen_h = True
            elif unit == 'm':
                if not seen_h or (i < len(s) and s[i].isdigit()):
                    raise ValueError("descending order violation")
                if n >= 60:
                    raise ValueError("minutes must be < 60")
                total += n * 60
            else:   # s
                if i < len(s) and s[i].isdigit():
                    raise ValueError("descending order violation after hours")
                if n >= 60:
                    raise ValueError("seconds must be < 60")
                total += n
        elif s[i].isdigit():
            continue
        else:
            raise ValueError(f"invalid character: {s[i]}")
    return total
