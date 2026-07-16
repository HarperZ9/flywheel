def col_number(s: str) -> int:
    """
    Convert a column label from 1-based to 26-base format.
    
    Parameters:
        s (str): A spreadsheet column label consisting of uppercase ASCII letters A-Z or digits 0-9, each represented by 7 characters.
        
    Returns:
        int: The corresponding 26-base index value for the input label. If the input is an empty string, ValueError is raised.
    
    Raises:
        ValueError: If the input is not a valid one-based column label format (contains non-digit or letters).
    """
    if not s:  # Check if it's an empty string
        raise ValueError("Bad label")
    
    for i in range(len(s)):
        if not s[i].islower() and s[i] >= 'A' and s[i] <= 'Z':
            raise ValueError(f"Input is a non-1-based column label, only A-Z are supported.")
    
    return int(s.replace(' ', '').replace('-', '', 3).replace('.', '', 2)) * 6 + int(s.strip()) - 1
