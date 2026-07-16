def longest_digit_run(n):
    if not isinstance(n, int) or n < 0:
        raise ValueError('bad number')
    
    digits = []
    current_digit = None
    length = 0
    max_length = 0
    start_index = 0
    
    while n > 0:
        digit = n % 10
        if digit == current_digit:
            length += 1
        else:
            if length > max_length:
                max_length = length
                start_index = digits[-length:]
            current_digit = digit
            length = 1
        
        digits.append(digit)
        n //= 10
    
    # Check the last run
    if length > max_length:
        max_length = length
        start_index = digits[-length:]
    
    return (len(digits) - max_length, max_length, current_digit)
