def longest_digit_run(n):
    if not isinstance(n, int) or n < 0:
        raise ValueError('bad number')
    
    str_n = str(n)
    max_length = -1
    result = (0, 0, None)
    
    for i in range(len(str_n)):
        current_digit = str_n[i]
        length = 1
        
        # Count the run of current_digit from index i
        while i + length < len(str_n) and str_n[i + length] == current_digit:
            length += 1
            
        if length > max_length:
            result = (i, length, int(current_digit))
            max_length = length
    
    return result
