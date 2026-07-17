def rle_decode(s):
    result = ''
    i = 0
    
    while i < len(s):
        # Check for number and its length
        if s[i].isdigit():
            j = i + 1
            while j < len(s) and (s[j].isdigit() or s[j] == 'a' or s[j] == 'b'):
                j += 1
            count_str = s[i:j]
            # Convert count to integer, raise ValueError if not a positive integer
            try:
                count = int(count_str)
            except ValueError:
                raise ValueError("Malformed input")
            
            char = s[j]
            
            # Validate the character (if it's 'a' or 'b')
            if not char.isdigit():
                result += char * count
                i = j + 1
                continue
            
            # Raise ValueError for invalid characters
            raise ValueError('Invalid character in run-length encoded string')
        else:
            raise ValueError("Malformed input")
        
    return result
