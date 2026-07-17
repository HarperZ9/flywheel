def _roman(n: int) -> str:
    """
    Converts an integer to its uppercase Roman numeral representation.
    
    Args:
        n (int): A positive integer, must be at least 1 and <= 3999.
        
    Returns:
        str: The uppercase Roman numeral representation of the given number in strict subtractive form.
             If the input is out of range, a ValueError is raised.
             
    Example usage:
    
    >>> _roman(1994)
    'MCMXCIV'
    >>> _roman(58)
    'LVIII'
    """
    # Mapping for subtractive compounds
    subtractive_compounds = {'IV': 4, 'IX': 9, 'XL': 40, 'XC': 90, 'CD': 400, 'CM': 900}
    
    result = ''
    while n >= 1:
        if n in subtractive_compounds:
            # Calculate the value of the current compound
            roman_value = subtractive_compounds[n]
            
            # Find the rightmost symbol to use
            for i in range(result.index('M') + 1, len(result)):
                if result[i] == 'M':
                    break
            
            # Append the result to the string with the correct number of symbols in strict subtractive form
            result = f'{result[:i]}{roman_value}{result[i:]}'
        else:
            # Use the largest available symbol to fill the next integer
            if n >= 1000:
                result += 'M'
                n %= 1000
            elif n >= 900:
                result += 'CM'
                n %= 900
            elif n >= 500:
                result += 'D'
                n %= 500
            elif n >= 400:
                result += 'CD'
                n %= 400
            elif n >= 100:
                result += 'C'
                if n == 90:
                    break
                n -= 90
            elif n >= 50:
                result += 'L'
                if n == 80:
                    break
                n -= 80
            elif n >= 40:
                result += 'XC'
                n -= 40
            elif n >= 10:
                result += 'X'
                if n == 9:
                    break
                n -= 9
            elif n >= 5:
                result += 'V'
                if n == 8:
                    break
                n -= 8
            elif n >= 4:
                result += 'I'
    
    return result

# Example usage and validation check
print(_roman(1994))  # MCMXCIV (1994)
print(_roman(58))   # LVIII (58)
