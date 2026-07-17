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
            was_upper, span_uppers = False, []
            while i < n and (s[i] == '_' or s[i].isupper()):
                if s[i].isupper():
                    if not was_upper:
                        span_uppers.clear()
                    span_uppers.append(i)
                    was_upper = True
                else:   # '_'
                    span_uppers.clear()
                    was_upper = False
                i += 1
            if i < n and s[i].lower() != s[i]:
                if was_upper and len(span_uppers) > 1:
                    out.append(s[span_uppers[-2]] + ''.join(s[j] for j in span_uppers[-2:]))
                    start = span_uppers[-2]
                    i = span_uppers[-1]
                else:
                    out.append(s[start:i])
            if i < n and not was_upper and s[i].isdigit():
                out.append(s[start:i])
                continue
        while i < n and s[i] == '_':
            i += 1
        start = i
    return out
