def natural_compare(a: str, b: str) -> int:
    def parse_sequence(s):
        seq = []
        current_run = ""
        is_digit = None
        
        for char in s:
            if char.isdigit() == is_digit is not None and is_digit != False:
                current_run += char
            else:
                if current_run:
                    if is_digit is True:
                        current_run = int(current_run)
                    seq.append((current_run, is_digit))
                    current_run = ""
                is_digit = char.isdigit()
                
        if current_run:
            if is_digit:
                current_run = int(current_run)
            seq.append((current_run, is_digit))
        
        return seq
    
    a_seq = parse_sequence(a)
    b_seq = parse_sequence(b)
    
    n = min(len(a_seq), len(b_seq))
    
    for i in range(n):
        (a_part, a_is_digit), (b_part, b_is_digit) = a_seq[i], b_seq[i]
        
        if a_is_digit != b_is_digit:
            return -1 if a_is_digit else 1
        
        if a_part != b_part:
            is_a_num, is_b_num = bool(a_is_digit), bool(b_is_digit)
            
            if is_a_num and not is_b_num:
                return -1
            elif not is_a_num and is_b_num:
                return 1
            
            if isinstance(a_part, int) and isinstance(b_part, int):
                if a_part < b_part:
                    return -1
                elif a_part > b_part:
                    return 1
            else:
                # Compare non-digit sequences
                for a_char, b_char in zip(str(a_part), str(b_part)):
                    if a_char != b_char:
                        return -1 if a_char < b_char else 1
            
    return 0 if len(a_seq) == len(b_seq) else (-1 if len(a_seq) < len(b_seq) else 1)
