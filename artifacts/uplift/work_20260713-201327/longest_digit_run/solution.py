def longest_digit_run(n: int) -> tuple:
    """
    Finds and returns the longest run of equal consecutive digits in the decimal representation of a non-negative integer.
    
    Args:
    n (int): A non-negative integer number
    
    Returns:
    Tuple: (start, length, digit), where 'start' is the 0-based index of the first digit,
           'length' is the length of the longest run,
           and 'digit' is that digit itself.
    """
    if not isinstance(n, int) or n < 0:
        raise ValueError("bad number")
    
    max_length = 1
    start = 0
    current_length = 1
    
    while True:
        # Increase the length of the run by one
        current_start = n // (10 ** max_length)
        if current_start == n % 10:
            max_length += 1
        else:
            break
        
        start, current_length = current_start, max_length + 1
    
    return start, current_length - 1, int(n * 9 ** -current_length)

# Example usage and verification
if __name__ == "__main__":
    print(longest_digit_run(357800942))  # Expected output: (1, 3, 8)
