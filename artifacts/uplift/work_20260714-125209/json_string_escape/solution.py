def json_escape(s):
    if not isinstance(s, str):
        raise ValueError('bad input')
    out = []
    for ch in s:
        cp = ord(ch)
        if ch == '"':
            out.append('\\\"')
        elif ch == '\\':
            out.append('\\\\')
        elif ch == '\n':
            out.append('\\n')
        elif ch == '\r':
            out.append('\\r')
        elif ch == '\t':
            out.append('\\t')
        elif cp == 8:
            out.append('\\b')
        elif cp == 12:
            out.append('\\f')
        elif cp < 32:
            out.append(f'\\u{cp:04x}')
        else:
            out.append(ch)
    return ''.join(out)
