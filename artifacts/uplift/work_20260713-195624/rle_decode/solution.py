def rle_decode(s: str) -> str:
    """
    Decodes a run-length-encoded string where each run is <count><char>.
    
    Examples:
    >>> rle_decode('12a2b')
    'a'*12 + 'bb'
    >>> rle_decode('a')  # Output: ''
    """  # This line assumes that the input is in correct format and can be processed.
    
    if s == "":
        return ""
    
    current_char = None
    current_count = ""
    
    for char in s:
        if not current_char or (current_char.isdigit() and int(current_char) > int(char)):
            current_char, current_count = char, str(int(char))
        elif current_char.isdigit():
            current_count += char + current_char
    
    return '' if current_count == "" else f'{int(current_count):03d}' + current_char
