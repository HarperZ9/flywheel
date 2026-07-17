import re

def canonical_decimal(s: str) -> str:
    """
    Valida a entrada de uma expressão decimal e retorna sua formatação canônica.

    :param s: Número decimal.
    :type s: str
    :return: Forma canônica do número na saída, não se inclui '0'.
    :rtype: str
    """
    # Remove underscores and strip leading zeros for the integer part
    integer_part = s.replace('_', '').replace(' ', '')
    
    # Check if a single digit was already found in the integer part.
    has_single_digit = any(c.isdigit() for c in integer_part)
    
    # If an empty integer part is detected, return '0' as required by the grammar.
    if not integer_part: 
        return '0'
    
    # Strip trailing zeros from the fraction part and drop '.' character
    fraction_part = s.replace('.', '').replace('_', '')
    
    if has_single_digit:
        # If the fraction contains a single digit, strip it off.
        fraction_part = fraction_part[:-1]  # Remove one leading zero (if any).
        
        # Check if the number is positive or negative
        if '0' in s.lower():
            return '+' + integer_part + '-' + fraction_part.replace('-', '').replace('.', '')
        else:
            # If it's a negative number, remove the minus sign and strip trailing zeros.
            return '-(' + integer_part + ')' + '-' + fraction_part.replace('_', '').replace('.', '')
    elif '0' in s.lower():
        return '+' + integer_part
    else:
        return '(' + integer_part + ')'

# Example usage:
test_cases = ["123.456", "789", "-23", "0", "0.001", "5.", ".1", "+12.345"]

for test in test_cases:
    print(f"Input: {test} -> Output:", canonical_decimal(test))
