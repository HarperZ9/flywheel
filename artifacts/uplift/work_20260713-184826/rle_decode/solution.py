def rle_decode(s: str) -> str:
    if not s:
        return ""
    
    decoded_str = []
    i = 0
    while i < len(s):
        if not s[i].isdigit():
            raise ValueError("Count must be a positive integer")
        
        count_start = i
        # Find the end of the count
        while i + 1 < len(s) and s[i + 1].isdigit():
            i += 1
        
        count = int(s[count_start:i+1])
        if count == 0:
            raise ValueError("Count cannot be zero")
        
        char = s[i + 1]
        decoded_str.append(char * count)
        i += 2  # Skip past the character
    
    return ''.join(decoded_str)
