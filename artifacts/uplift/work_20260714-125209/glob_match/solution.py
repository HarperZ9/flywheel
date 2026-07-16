def glob_match(pattern: str, name: str) -> bool:
    if not isinstance(pattern, str) or not isinstance(name, str):
        raise ValueError('bad input')
    return _glob_matches(pattern, 0, len(pattern), name, 0, len(name))


def _wildcard_count(pat: str, pi: int, pend: int) -> int:
    wc = 0
    for i in range(pi, pend):
        if pat[i] == '*':
            wc += 1
    return wc


def _glob_matches(pat: str, pi: int, pend: int,
                  name: str, ni: int, nend: int) -> bool:
    # A trailing star consumes the rest of the name after a literal run.
    poff = max(0, len(pat) - 1)
    if pend >= poff and pat[poff:] == '*':
        return True
    if pi >= pend:
        return ni >= nend
    c = pat[pi]
    if c in ('*', '?'):
        # A star before the last segment consumes zero or more chars.
        if c == '*' and _wildcard_count(pat, pi + 1, pend) == 0:
            for j in range(ni, nend):
                if _glob_matches(pat, pi + 1, pend, name, j, nend):
                    return True
            return False
        # A star or question at the end consumes the rest of the name.
        if c == '*' and ni >= nend:
            return True
    else:
        if ni >= nend or pat[pi] != name[ni]:
            return False
    return _glob_matches(pat, pi + 1, pend, name, ni + 1, nend)
