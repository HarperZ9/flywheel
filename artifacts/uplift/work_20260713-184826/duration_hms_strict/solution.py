def parse_duration_strict(s: str) -> int:
    if not s:
        raise ValueError("Empty string")

    units = {'h': 3600, 'm': 60, 's': 1}
    total_seconds = 0
    current_unit = None

    for i, char in enumerate(s):
        if char.isdigit():
            if current_unit is None:
                raise ValueError("Number with no unit after it")
            num = int(char)
            if i > 0 and s[i - 1].isdigit() and char == '0':
                raise ValueError("Leading zero in number")
            if (current_unit == 'm' or current_unit == 's') and num >= 60:
                raise ValueError(f"Number {num} for unit {current_unit.upper()} is out of range")
            total_seconds += num * units[current_unit]
        elif char in units:
            if current_unit is not None and (char == 'm' or char == 's'):
                raise ValueError("Units must appear in strictly descending order")
            current_unit = char
        else:
            raise ValueError(f"Invalid character {char}")

    return total_seconds
