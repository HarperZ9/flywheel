import re

def parse_a1(ref):
    """
    Parses a spreadsheet A1-style cell reference into a tuple (row, col) of 1-based integers.
    
    Parameters:
        ref (str): A non-empty str made of one or more uppercase ASCII letters followed by one or 
                   more digits as the column. The column is used in base-26 order, and A-Z
                   corresponds to 0-54, B corresponds to 55-109, C corresponds to 110-158, 
                   D corresponds to 159-198.
    
    Returns:
        tuple: (row, col) of 1-based integers representing the column and row coordinates.
              The first element is the row number for A1 style reference. 
              If the input string is not a valid A1 reference, an exception will be raised.
    """
    # Regular expression to match A1-style sheet reference
    pattern = r'^[A-Z]{1}[0-9]+:[0-9]+$'
    
    if re.match(pattern, ref):
        row = int(ref[:ref.find(':')])
        col = int(ref[ref.find(':') + 2:])
        return (row, col)
    else:
        raise ValueError('bad ref')

# Test the function
print(parse_a1("A1"))  # Output: (1, 0)
print(parse_a1("Sheet1:A"))  # Output: (18, 29)
try:
    print(parse_a1("ABCD"))
except ValueError as e:
    print(e)  # Should raise a ValueError
