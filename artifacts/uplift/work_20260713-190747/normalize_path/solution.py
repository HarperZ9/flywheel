def normalize_path(p):
    if not isinstance(p, str):
        raise ValueError('bad path')
    if not p.startswith('/'):
        raise ValueError('not absolute')

    segments = []
    parts = p[1:].split('/')
    
    for part in parts:
        if part == '' or part == '.':
            continue
        elif part == '..':
            if segments and segments[-1] != '/':
                segments.pop()
            elif not segments:
                # Already at the root, so doing .. has no effect.
                pass
        else:
            segments.append(part)
    
    return '/' + '/'.join(segments).rstrip('/')
