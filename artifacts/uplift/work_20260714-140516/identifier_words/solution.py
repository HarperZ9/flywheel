import string

def split_identifier(s):
    if not s:
        return []
    if any(c not in string.ascii_letters + string.digits + '_' for c in s):
        raise ValueError('bad char')
    out = []
    i, n = 0, len(s)
    while i < n and s[i] == '_':
        i += 1
    while i < n:
        start = i
        if s[i].isdigit():
            i += 1
            while i < n and s[i].isdigit():
                i += 1
            out.append(s[start:i])
        else:       # letter
            was_upper, first = False, True
            u_start = i    # index of the first uppercase letter in this sequence
            while i < n and (s[i].isalpha() or s[i] == '_'):
                if s[i].isupper():
                    u_start = i
                    was_upper = not first
                elif s[i].isdigit():
                    break
                first = False
                i += 1
            # If an acronym followed by a letter, steal the last uppercase from it.
            if i < n and s[i].isalpha() and u_start > start:
                j = u_start + 1
                while j < i - 1:           # collapse down to one upper per word (the Python snake_to_camel rule)
                    out.append(s[start:j])
                    start = j
                    while j < i and s[j].isupper():
                        j += 1
            if start < i:
                out.append(s[start:i])
        while i < n and s[i] == '_':
            i += 1
    return out
