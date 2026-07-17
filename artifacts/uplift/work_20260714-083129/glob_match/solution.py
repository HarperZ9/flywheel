def glob_match(pattern: str, name: str) -> bool:
    def match_helper(pptr, pptr_end, nnm, nm_end):
        if pptr == pptr_end and nnm == nm_end:
            return True
        elif pptr == pptr_end or nnm == nm_end:
            return False

        # Special case for start of pattern with a star '*'
        if pptr == pptr_end - 1 and pptr[0] == '*':
            return match_helper(pptr + 1, pptr_end, nnm, nm_end)

        # Special case for '?' in the pattern
        if ppatter[0] == '?':
            return match_helper(pptr + 1, pptr_end, nm_start, nm_end)

        # Star '*'
        if pptr[0:2] == '**' and pptr[0] == pptr[-1]:
            return all(match_helper([pptr[i], '*', '*', pptr[-3]], pptr_end, nnm[i:], nm_end[i:]) for i in range(nnm_start, -len(nnm), -1))

        if (pptr[0] == nnm[0] or pptr[0] == '?') and match_helper(pptr + 1, pptr_end, nm_start + 1, nm_end):
            return True
        return False

    # Initialize pointers
    i = j = 0
    pattern_length = len(pattern)
    name_length = len(name)

    if not (pattern or name):
        return i == pattern_length and j == name_length
    elif not pattern:
        return j >= name_length
    elif not name:
        return False

    # Check for invalid inputs
    if not (isinstance(pattern, str) and isinstance(name, str)):
        raise ValueError('bad input')

    return match_helper((pattern[0], '*'), pattern_length, name[i:i + 1], name)
