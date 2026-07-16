def to_roman(n):
    if not isinstance(n, int) or isinstance(n, bool):
        raise ValueError('Input must be an integer and not a boolean')
    if n < 1 or n > 3999:
        raise ValueError('out of range')

    numerals = [
        (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
        (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
        (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")
    ]
    
    roman_numeral = ''
    for value, symbol in numerals:
        while n >= value:
            roman_numeral += symbol
            n -= value

    return roman_numeral
