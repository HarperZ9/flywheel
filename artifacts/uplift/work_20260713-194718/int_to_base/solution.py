def in_base(n: int, base: int) -> str:
    if not (2 <= base <= 36):
        raise ValueError('bad base')
    if not isinstance(n, int) or n == bool(1):
        raise ValueError('bad number')
    
    if n < 0:
        sign = '-'
        n = -n
    else:
        sign = ''
        
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    result = []
    
    while n > 0:
        n, remainder = divmod(n, base)
        result.append(digits[remainder])
        
    if not result:
        return '0'
        
    return sign + ''.join(result[::-1])
