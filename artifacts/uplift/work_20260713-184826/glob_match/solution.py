def glob_match(pattern: str, name: str) -> bool:
    if not isinstance(pattern, str) or not isinstance(name, str):
        raise ValueError('bad input')
    
    # Early return for empty pattern
    if pattern == '':
        return name == ''
    
    # Check if pattern starts with '*' (matches any characters including none)
    if pattern[0] == '*':
        return glob_match(pattern[1:], name) or (name and glob_match('*', name[1:]))
    
    # If the first character matches or both are '?'
    if len(pattern) > 0 and (pattern[0] == '?' or pattern[0] == name[0]):
        return glob_match(pattern[1:], name[1:])
    
    # No match found
    return False
