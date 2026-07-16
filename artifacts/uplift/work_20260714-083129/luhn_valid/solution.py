def luhn_valid(s: str) -> bool:
    if not s or not isinstance(s, str):
        raise ValueError('bad number')
    
    for char in s:
        if not char.isdigit():
            raise ValueError('bad number')
    
    odd_sum = 0
    even_sum = 0
    
    for i, char in enumerate(reversed(s)):
        num = int(char)
        
        # Double every second digit from the right (even positions)
        if i % 2 == 1:
            doubled_num = num * 2
            
            # If the result is greater than 9, subtract nine
            if doubled_num > 9:
                doubled_num -= 9
                
            even_sum += doubled_num
        else:
            odd_sum += num
    
    return (odd_sum + even_sum) % 10 == 0
