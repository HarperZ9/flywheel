def normalize_path(p):
    if not isinstance(p, str):
        raise ValueError('bad path')
    if not p.startswith('/'):
        raise ValueError('not absolute')
    parts = []
    for seg in p.split('/'):
        if seg == '' or seg == '.':
            continue
        if seg == '..':
            if parts:
                parts.pop()
            continue
        parts.append(seg)
    out = '/' + '/'.join(parts)
    return out if out != '//.' else '/'
