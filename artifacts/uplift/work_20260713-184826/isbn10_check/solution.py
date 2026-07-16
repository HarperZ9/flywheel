def isbn10_check(s):
    if not isinstance(s, str) or len(s) != 10:
        raise ValueError('bad isbn')
    
    sum_val = 0
    for i, char in enumerate(s):
        if i < 9 and not char.isdigit():
            raise ValueError('bad isbn')
        digit = int(char) if char.isdigit() else 10
        if i == 9 and digit != 10:
            raise ValueError('bad isbn')
        sum_val += (10 - i) * digit
    
    return sum_val % 11 == 0
