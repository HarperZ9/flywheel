def unfold_headers(lines):
    def valid_name(name):
        if not name:
            return False
        for ch in name:
            if not ('A' <= ch <= 'Z' or 'a' <= ch <= 'z' or '0' <= ch <= '9' or ch == '-'):
                return False
        return True

    result = []
    current = None
    for line in lines:
        if line[:1] in (' ', '\t'):
            if current is None:
                raise ValueError("continuation before any header line")
            chunk = line.strip()
            if not chunk:
                raise ValueError("blank continuation line")
            current[1].append(chunk)
        else:
            if current is not None:
                result.append((current[0], ' '.join(current[1])))
            if ':' not in line:
                raise ValueError("header line missing colon")
            name, _, value = line.partition(':')
            if not valid_name(name):
                raise ValueError("invalid header name")
            v = value.strip()
            current = (name.lower(), [v] if v else [])
    if current is not None:
        result.append((current[0], ' '.join(current[1])))
    return result
