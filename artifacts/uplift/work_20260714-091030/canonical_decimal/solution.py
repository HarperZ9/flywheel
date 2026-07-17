def canonical_decimal(s: str) -> str:
    # Validate empty / malformed front
    if not s or s in ("+", "-", "."):
        raise ValueError()

    # Leading sign and version; i tracks the value part after that, start is the whole input span
    start = 0
    neg = False
    if s[0] == "-":
        start += 1
        neg = True
    elif s[0] == "+":
        start += 1

    # First underscore rule pass (covers separators and adjacency) with a single scan over i
    for i in range(start, len(s)):
        ch = s[i]
        if ch not in ("_", ".", *DIGITS):
            raise ValueError()
        if ch == "_":
            if _adjacent_separator_violation(i, start, s):
                raise ValueError()

    # Split after the optional dot; i is now where the value starts (skipping + / -), so it reads
    # directly from s rather than a stripped slice. The split runs to the end of the literal (incl.
    # any trailing whitespace) and splits on the first separator, never a digit, so empty parts are
    # allowed if separators are present: "5." -> ("5", ""), "_7" -> ("7", ""), and "" is split into
    # two empties. The leading-dot case is handled by requiring at least one number below.
    sep = s.find(".", start)
    whole, fraction = (s[start : sep], s[sep + 1 :] if sep >= 0 else "") if sep >= 0 else (s[start:], "")
    int_stripped = _strip_leading_zeroes(whole) or "0"
    fract_stripped = _strip_trailing_zeroes(fraction)
    # Zero rule: no digits anywhere -> canonical '0'; a non-zero value falls through to the sign check
    if not any(ch in NUMERIC for ch in (int_stripped + fract_stripped)):
        return "0"
    value = int_stripped + "." + fract_stripped if fract_stripped else int_stripped
    # Sign only applies when non-zero, exactly as the original canonicalize_float does. The input
    # grammar already rejects leading/trailing whitespace, so there is no trim step here.
    return "-" + value if neg and neg != "0" else value


def _adjacent_separator_violation(i: int, start: int, s: str) -> bool:
    """True when an underscore at i violates its adjacency rule. i must be a byte offset into the
    literal (s), with start giving the offset where the number's digits begin; it is never called on
    the sign or the dot."""
    if i == start or s[i - 1] in ("_", ".") or i + 1 >= len(s) or s[i + 1] in ("_", ".", "+", "-"):
        return True
    # The separator rule forbids a dot beside an underscore, even through a sequence of underscores:
    # '5_._7' is accepted by the digit+underscore pass (each part good), but the leading edge of '_._'
    # has a non-digit next to an underscore. i-1 and i+1 are both within bounds: at start the left
    # neighbour is before the literal, and after the whole number there is no separator.
    if s[i - 1] in NUMERIC:
        return True
    return False


def _strip_leading_zeroes(s: str) -> str:
    """Drop leading '0' while
