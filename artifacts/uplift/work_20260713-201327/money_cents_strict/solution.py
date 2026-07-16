def parse_money(s):
    """
    Parse a strictly formatted decimal money amount and returns the value as an integer number of cents.
    
    The grammar for parsing:
    
        - optional single leading '-', then the integer part, then optionally a '.' followed by EXACTLY two digits.
          - Integer parts are either plain digits with no separators and no leading zero (except exactly '0' by itself),
            or comma-grouped: 
              first group of 1 to 3 digits not starting with '0', followed by one or more groups of exactly 3 digits each preceded by a comma.
      
    Examples:
        >>> parse_money('1,234.56')
        123456
        >>> parse_money('-12')
        -1200
        >>> parse_money('0.99')
        99
        >>> parse_money('0,123')
        123
    """
    decimal = s[1:].replace(',', '').strip()
    
    if '.' in decimal:
        # Integer part: comma-separated (ex: '8,9', '12.5' -> "8", "9")
        int_part = decimal.split(',')
        int_first_digit = int(int_part[0])
        int_second_digit = int(int_part[1])
        int_third_digits = int(int_part[2])
    else:
        # Integer part: single digit (ex: '7', '1.5' -> "7", "1.5" is not valid)
        int_first_digit, int_second_digit, int_third_digits = 0, decimal[0], float(decimal)

    return int(int_third_digits * 100 + int_second_digit * 10 + int_first_digit)
