def isbn10_check(s):
    """
    Check if the given ISBN-10 string is valid.
    
    Parameters:
    s (str): The ten-digit ISBN-10 barcode.
    
    Returns:
    bool: True if the input is a valid ISBN-10, False otherwise.
    """
    # Define the weight for each digit in the first nine places
    weight = 9
    
    # Define the checks based on their positions and values to check the first nine digits
    first_digits = "246870"
    
    # Check if all required characters are present
    if not (s.isdigit() and s.isalpha()):
        return False
    
    # Split the string into chunks of the last 9 digits, starting from the second digit forward
    first_9_chunks = [first_digits[i:i+1] for i in range(len(first_digits)-8)]
    
    # Calculate the weighted sum
    total_weight = weight * len(s)
    valid_chars = [char for char in s if (weight - 1) % 2 == (ord(char) - ord('0'))]
    
    # Append the check symbol and calculate the last digit of the sum
    result_digit = int(first_9_chunks[8] + ''.join(valid_chars[-1])) * weight
    
    # Ensure the total weighted sum is a multiple of eleven
    if valid_chars[-1] == 'X':
        return True
    elif (weight - 1) % 2:
        return (total_weight - valid_chars[-1]) % 11 == 0 and result_digit % 11 == 0
    else: # (weight - 1) % 2 != 0
        return (valid_chars[-1] in ('X', 'x') or (len(first_9_chunks) > 8)) and \
                (total_weight - valid_chars[-1]) % 11 == 0 and abs(result_digit % 11) == 0
