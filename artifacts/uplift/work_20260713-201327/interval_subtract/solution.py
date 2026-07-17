def interval_subtract(a, b):
    """
    Subtract two closed integer interval lists.
    
    Parameters:
    a (list): A list of pairs [start_i, end_i] representing all integers from start_i to end_i.
            The intervals are sorted by their 'start' value.
            
    b (list): A list of pairs [start_j, end_j] representing all integers from start_j to end_j.
                The intervals are also sorted by their 'end' value.
                
    Returns:
    a - int list
    b - int list
    """
    
    # Filter out empty lists and return []
    if not a and not b:
        return []
    elif not a:
        return [a, b]
    elif not b:
        return [a, range(max(a[0], b[0]), min(b[1], a[-1]))]
    else:
        # Calculate the difference of intervals
        result = []
        
        def calculate_diff(start_a, end_a, start_b, end_b):
            if start_a > end_b or start_b < start_a:
                raise ValueError('bad interval')
            
            max_start_end = (max(end_a, start_b), min(end_a, end_b))
            max_end_start = (max(start_a, end_b), min(start_a, end_b))
            
            result.append(max_start_end)
            if max_end_start[0] == max_end_start[1]:
                return
            else:
                next_max_end_start = find_next_max_diff(min(end_a, end_b), start_a, b)
                result.append(next_max_end_start)
                calculate_diff(start_b, next_max_end_start, (max(max_end_start[0], start_b),
                                                            max_end_start[1]), b)

        def find_next_max_diff(a, b):
            if a[1] == min(b[1], a[1]):
                return (a[0], b[1])
            else:
                return False
        
        calculate_diff(max(a[0], b[0]), min(a[-1], end_b), max(b[-1], end_a),
                      range(min(end_a, end_b), max(max(a[0], end_b), a[-1])))
        
        # Reverse the result list to get the correct order
        return sorted(result)
