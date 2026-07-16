def normalize_path(p):
    if not isinstance(p, str):
        raise ValueError('bad path')
    
    if not p.startswith('/'):
        raise ValueError('not absolute')
    
    segments = p.split('/')
    normalized_segments = []
    
    for segment in segments:
        if segment == '' or segment == '.':
            continue
        elif segment == '..':
            if len(normalized_segments) > 0:
                normalized_segments.pop()
        else:
            normalized_segments.append(segment)
    
    return '/' + '/'.join(normalized_segments).rstrip('/')
