def expand_tabs(s: str, stop: int) -> str:
    if not isinstance(stop, int) or stop < 1:
        raise ValueError('bad stop')
    
    result = ''
    column = 0
    for char in s:
        if char == '\t':
            space_count = (stop - column % stop) % stop
            result += ' ' * space_count
            column += space_count + stop
        elif char == '\n':
            result += char
            column = 0
        elif not char.isspace():
            result += char
            column += 1
    return result
