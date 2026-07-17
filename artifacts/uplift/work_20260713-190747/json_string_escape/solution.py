def json_escape(s):
    if not isinstance(s, str):
        raise ValueError('bad input')
    
    def escape_char(c):
        if c == '"':
            return '\\"'
        elif c == '\\':
            return '\\\\'
        elif c == '\n':
            return '\\n'
        elif c == '\r':
            return '\\r'
        elif c == '\t':
            return '\\t'
        elif c == '\x08':
            return '\\b'
        elif c == '\x0c':
            return '\\f'
        elif ord(c) < 32:
            return '\\u{:04x}'.format(ord(c))
        else:
            return c
    
    return ''.join(escape_char(c) for c in s)
