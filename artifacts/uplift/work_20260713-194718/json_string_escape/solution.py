def json_escape(s):
    if not isinstance(s, str):
        raise ValueError('bad input')
    
    result = ""
    for char in s:
        if ord(char) == 8:
            result += '\\b'
        elif ord(char) == 9:
            result += '\\t'
        elif ord(char) == 10:
            result += '\\n'
        elif ord(char) == 11:
            result += '\\v'
        elif ord(char) == 12:
            result += '\\f'
        elif ord(char) == 32:
            continue
        elif ord(char) <= 31 or ord(char) >= 128:
            result += '\\u{:04x}'.format(ord(char))
        else:
            if char in ['"', '\\']:
                result += '\\'
            result += char
    return result
