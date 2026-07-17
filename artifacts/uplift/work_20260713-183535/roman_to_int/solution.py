def roman_to_int(s: str) -> int:
    """
    Convert a Roman numeral string to an integer.
    
    Args:
        s (str): The Roman numeral string to be converted.
        
    Returns:
        int: The corresponding integer value of the Roman numeral string.
    """
    # Define mapping between Roman numerals and their integers
    roman_numerals = {
        "I": 1,
        "V": 5,
        "X": 10,
        "L": 50,
        "C": 100,
        "D": 500,
        "M": 1000
    }
    
    # Initialize the result as a default value if the string is empty or contains only one character
    total_sum = 0
    
    for char in s:
        # If there are more than 4 numerals left, subtract from the total sum
        if len(s) >= 3 and roman_numerals[char] < roman_numerals[s[-1]]:
            total_sum -= roman_numerals[char]
        
        else:  # Otherwise, add to the total sum
            total_sum += roman_numerals[char]
    
    return total_sum
