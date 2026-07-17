import json

def json_escape(s):
    if not isinstance(s, str):
        raise ValueError('bad input')
    
    escape_map = {
        r'\': backslash followed by a double quote',
        r'\\': backslash, followed by a double quote,
        r'n': backslash, followed by letter n,
        r'r': backslash, followed by letter r,
        r't': backslash, followed by letter t,
        r'b': backslash, followed by letter b,
        r'f': backslash, followed by letter f,
        r'\x8': backslash, followed by letter u, then four lowercase hexadecimal digits of the code point (for control characters),
    }
    
    # Replace non-escape sequences
    for escape in escape_map.keys():
        s = s.replace(escape, escape_map[escape])
    
    return json.dumps(s)
