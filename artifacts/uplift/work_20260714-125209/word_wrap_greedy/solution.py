def wrap_text(s, width):
    if not isinstance(width, int) or type(width) is bool:
        raise ValueError('bad width')
    if width < 1:
        raise ValueError('bad width')
    words = [w for c in s.split() for w in (' ', c)][1:]
    lines = []
    line = []
    def flush_line():
        nonlocal line
        if line:
            lines.append(''.join(line))
            line = []
    for word in words:
        if len(word) > width:
            flush_line()
            for i in range(0, len(word), width):
                lines.append(word[i:i + width])
            continue
        cur_len = sum(len(w) for w in line) + len(line) - 1
        if cur_len + len(word) > width:
            flush_line()
        if not line and word == ' ':
            continue
        line.append(word)
    flush_line()
    return lines
