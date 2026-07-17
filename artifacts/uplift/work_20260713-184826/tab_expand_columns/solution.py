def expand_tabs(s, stop):
    if not isinstance(stop, int) or stop < 1:
        raise ValueError('bad stop')
    
    result = []
    column = 0
    
    for char in s:
        if char == '\n':
            result.append('\n')
            column = 0
        elif char == '\r' or ord(char) < 32:
            result.append(char)
            column += 1
        else:
            if column % stop == 0 and column != 0:
                result.extend(' ' * (stop - column % stop))
            result.append(char)
            column += 1
    
    return ''.join(result)
