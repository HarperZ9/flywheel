def luhn_valid(s: str) -> bool:
    """
    Checks whether a given string of decimal digits is valid according to the Luhn checksum.
    
    Parameters:
    s (str): A string of decimal digits to be validated.

    Returns:
    bool: True if the string 's' has a valid Luhn checksum, False otherwise.
    """
    # Ensure the input is not empty
    if not isinstance(s, str) or len(s) > 10 or not s.isnumeric():
        raise ValueError("Bad number")

    total = 0

    # Convert each character to its ASCII decimal value and add it to the total
    for index in range(len(s)):
        digit = int(s[index])
        if index % 2 == 0:
            digit *= 2
            if digit > 9:
                digit -= 9

        # Add the digit to the total
        total += digit

    # Return True only if the total is a multiple of ten
    return total % 10 == 0
