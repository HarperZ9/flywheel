def expand_tabs(s: str, stop: int) -> str:
    if not isinstance(stop, int) or stop < 1 or type(stop) is bool:
        raise ValueError('bad stop')
    
    result = []
    col = 0
    
    for char in s:
        if char == '\t':
            # Calculate number of spaces needed to reach next tab stop
            num_spaces = (stop - col % stop) % stop
            result.extend([' ']*num_spaces)
            col += num_spaces
        elif char == '\n':
            result.append('\n')
            col = 0
        else:
            result.append(char)
            if char != '\r':  # Handle newline and tab separately
                col += 1
    
    return ''.join(result)
