def isbn10_check(s):
    if not isinstance(s, str) or len(s) != 10:
        raise ValueError('bad isbn')
    
    digits = list(s)
    
    for i in range(9):
        if not digits[i].isdigit():
            raise ValueError('bad isbn')
        
        num = int(digits[i])
        weight = 10 - i
        if num > 9:
            raise ValueError('bad isbn')
        
        if num == 10 and digits[i] != 'X':
            return False
    
    if digits[9].lower() in ['x', '']:
        return False
    
    digit_sum = sum(num * weight for num, weight in zip(digits, range(10, 0, -1)))
    
    return digit_sum % 11 == 0
