def from_base(s: str, base: int) -> int:
    if not 2 <= base <= 36 or type(base) == bool:
        raise ValueError('bad base')
    
    s = s.strip()
    minus_sign_present = False
    
    if s.startswith('-'):
        if len(s) > 1 and s[1:].isdigit() and len(s) > 1:
            return -from_base(s[1:], base)
        elif not s[1:].strip().replace("-", "").isalnum():
            raise ValueError('bad digits')
        minus_sign_present = True
        s = s[1:]
    
    if s == "-":
        raise ValueError('bad digits')

    valid_chars = "0123456789abcdefghijklmnopqrstuvwxyz"
    value_map = {char: index for index, char in enumerate(valid_chars[:base])}
    
    total = 0
    for i, char in enumerate(s):
        if not char.isdigit() and char.lower() not in value_map:
            raise ValueError('bad digits')
        
        digit_value = value_map[char.lower()]
        
        if i > 0 and (minus_sign_present or (char.isdigit() and s[i-1].isdigit()) or (not minus_sign_present and not s[i-1].lower().isalpha())):
            total += -digit_value * base**i
        elif i > 0:
            total += digit_value * base**i
        else:
            total += digit_value
    
    if minus_sign_present:
        total *= -1

    return total
