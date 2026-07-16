def expand_tabs(s, stop):
    if not isinstance(stop, int) or isinstance(stop, bool) or stop < 1:
        raise ValueError('bad stop')
    out = []
    col = 0
    for c in s:
        if c == '\t':
            spaces = stop - (col % stop)
            out.append(' ' * spaces)
            col += spaces
        elif c == '\n':
            out.append(c)
            col = 0
        else:
            out.append(c)
            col += 1
    return ''.join(out)
