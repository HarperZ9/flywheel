def canonical_decimal(s: str) -> str:
    # Check if input is a valid decimal number according to the grammar
    if not (s and s[0] in "+-" or (s[0].isdigit() and '.' in s)):
        raise ValueError("Invalid input")
    
    sign = 1
    integer_part = ""
    fraction_part = ""
    underscore_error = False
    
    i = 0
    while i < len(s):
        if i == 0 and s[i] in "+-":
            # Check for a sign at the start
            sign = -1 if s[i] == '-' else 1
            i += 1
        elif s[i].isdigit():
            # Check for digit in integer part or fraction part
            if '.' not in (integer_part + fraction_part):
                integer_part += s[i]
            else:
                fraction_part += s[i]
        elif s[i] == '_':
            # Check if underscore is valid
            if i > 0 and i < len(s) - 1 and s[i-1].isdigit() and s[i+1].isdigit():
                pass
            else:
                underscore_error = True
                break
        else:
            # Invalid character
            raise ValueError("Invalid input")
        
        i += 1
    
    if underscore_error or not integer_part and not fraction_part:
        raise ValueError("Invalid input")
    
    # Remove underscores and leading zeros from the integer part
    integer_part = integer_part.replace("_", "")
    integer_part = integer_part.lstrip('0')
    if not integer_part:
        integer_part = '0'
    
    # Remove trailing zeros from the fraction part and handle special cases
    fraction_part = fraction_part.rstrip('0').lstrip('0')
    if fraction_part == "":
        fraction_part = ""
    elif fraction_part[0] == '.':
        fraction_part = "0" + fraction_part
    
    # Construct the canonical form
    result = integer_part + (("." + fraction_part) * bool(fraction_part))
    
    return sign < 0 and not result.startswith("0") and result != "-" and f"-{result}" or result
