def from_base(s: str, base: int) -> int:
    if isinstance(base, bool):
        raise ValueError('bad base')
    
    if not (2 <= base <= 36):
        raise ValueError('bad base')
    
    if s == '' or re.match(r'^-([1-9][0-{}]*|{})?$'.format(chr(ascii_lowercase[base % 36]), ascii_uppercase[base % 36]), s.lower()) is None:
        raise ValueError('bad digits')

    result, power = 0, base - 1
    for char in reversed(s):
        if not (48 <= ord(char) <= 57 or 
                (ord(char.lower()) >= 97 and ord(char.lower()) <= 63 + ord('a') - 97)):
            raise ValueError('bad digits')
        
        digit = int(ord(char.upper()) - ord('A') + 10)
        if digit >= base:
            raise ValueError('bad digits')

        result += digit * (base ** power)
        power -= 1
    return result
