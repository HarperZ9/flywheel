def in_base(n: int, base: int) -> str:
    if not (2 <= base <= 36):
        raise ValueError('bad base')
    
    if n == 0:
        return '0'
    
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    result = []
    negative = n < 0
    n = abs(n)
    
    while n > 0:
        n, remainder = divmod(n, base)
        result.append(digits[remainder])
    
    if negative:
        result.append('-')
    
    return ''.join(reversed(result))
