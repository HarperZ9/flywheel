def to_roman(n):
    if not (isinstance(n, int) and isinstance(n, bool) == False and 1 <= n <= 3999):
        raise ValueError('out of range')
    
    val = [
        (1000, 'M'), (900, 'CM'), (500, 'D'), (400, 'CD'),
        (100, 'C'), (90, 'XC'), (50, 'L'), (40, 'XL'),
        (10, 'X'), (9, 'IX'), (5, 'V'), (4, 'IV'), (1, 'I')
    ]
    
    roman_numeral = ''
    for value, symbol in val:
        while n >= value:
            roman_numeral += symbol
            n -= value
    
    return roman_numeral
