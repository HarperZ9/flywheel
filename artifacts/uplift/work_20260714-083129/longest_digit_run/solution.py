def longest_digit_run(n):
    if not isinstance(n, int) or n < 0:
        raise ValueError('bad number')
    
    # Convert integer to string for easier manipulation
    str_n = str(abs(n))
    max_length = start_of_max = length = i = digit_value = -1
    
    while i < len(str_n):
        current_digit = str_n[i]
        run_start_i = i
        
        # Extend the run if consecutive digits match
        while i + 1 < len(str_n) and str_n[i] == str_n[i+1]:
            i += 1
        
        length_of_run = i - run_start_i + 1
        if length_of_run > max_length:
            max_length, start_of_max, digit_value = length_of_run, run_start_i, int(current_digit)
    
    return (start_of_max, max_length, digit_value)
