def parse_template_fields(s):
    out = []
    text = []

    def flush():
        if text:
            out.append(('text', ''.join(text)))
            text.clear()

    i = 0
    n = len(s)
    while i < n:
        ch = s[i]
        if ch == '{':
            if i + 1 < n and s[i + 1] == '{':
                text.append('{')
                i += 2
                continue
            j = s.find('}', i + 1)
            if j == -1:
                raise ValueError("unterminated field")
            name = s[i + 1:j]
            if not name:
                raise ValueError("empty field name")
            first = name[0]
            if not ('A' <= first <= 'Z' or 'a' <= first <= 'z' or first == '_'):
                raise ValueError("invalid field name")
            for c in name[1:]:
                if not ('A' <= c <= 'Z' or 'a' <= c <= 'z' or '0' <= c <= '9' or c == '_'):
                    raise ValueError("invalid field name")
            flush()
            out.append(('field', name))
            i = j + 1
        elif ch == '}':
            if i + 1 < n and s[i + 1] == '}':
                text.append('}')
                i += 2
            else:
                raise ValueError("stray closing brace")
        else:
            text.append(ch)
            i += 1
    flush()
    return out
