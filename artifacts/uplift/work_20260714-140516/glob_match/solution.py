def glob_match(pattern: str, name: str) -> bool:
    if not isinstance(pattern, str) or not isinstance(name, str):
        raise ValueError('bad input')
    p = list(pattern)
    n = list(name)

    def _match(pindex: int, nstart: int) -> bool:
        for i in range(pindex, len(p)):
            c = p[i]
            if c == '*':
                if i + 1 < len(p):
                    # Try to consume zero characters at this position; the star
                    # attempts to match one more character each time until it runs
                    # out of name or the rest lines up.
                    return _match(i + 1, nstart) or (nstart < len(n)
                        and _match(pindex, nstart + 1))
                else:
                    # Trailing star: consume all remaining characters. This is the only
                    # place a lone star matches the empty string; it cannot reach here
                    # when there are more pattern bytes left to match.
                    return True
            elif c == '?':
                # ? consumes exactly one character; fail if out of name.
                nstart += 1
                if nstart > len(n):
                    return False
            else:
                # Literal. Consume precisely one matching byte at this position and
                # fail on any mismatch.
                if nstart >= len(n) or c != n[nstart]:
                    return False
                nstart += 1

        return nstart == len(n)

    return _match(0, 0)
