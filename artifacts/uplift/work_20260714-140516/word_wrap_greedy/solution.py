def wrap_text(s, width):
    if not isinstance(width, int) or type(width) is bool:
        raise ValueError('bad width')
    if width < 1:
        raise ValueError('bad width')
    words = [w for chunk in s.split() for w in (' ' + chunk).split()]
    lines = []
    cur = ''
    for word in words:
        cand = (cur + word).rstrip()
        if len(cand) > width:
            if cur:
                lines.append(cur)
                cur = ''
            while word:
                lines.append(word[:width])
                word = word[width:].lstrip()
            continue
        if cur:
            cur += ' ' + word
        else:
            cur = word
    if cur:
        lines.append(cur)
    return [line for line in (l.strip() for l in lines) if line]
