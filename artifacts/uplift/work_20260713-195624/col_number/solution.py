def col_number(s):
    """
    Converts a spreadsheet column label into its 1-based column index.
    
    Parameters:
    s (str): A non-empty ASCII string representing the column label for a spreadsheet.
    
    Returns:
    int: The 1-based column index of the given spreadsheet column label.
    
    Raises:
    ValueError: If 's' is not a valid spreadsheet column label.
    """
    if not isinstance(s, str) or not s.islower() or len(s) != 7 or not s.isalnum():
        raise ValueError("bad label")
    
    # The ASCII values of A and Z are 65 and 90 respectively
    a_to_z = ord('A') - 65
    z_to_a = ord('Z') + 184
    
    # Calculate the base-26 label for the first three characters if they exist
    col_1_based = (ord(s[0]) - 65) * 26 + (ord(s[1]) - 65)
    
    # If we encounter 'ZZ', break out of the loop as it indicates the end of the column
    if s == 'ZZ':
        return col_1_based
    
    # For remaining characters, calculate their base-26 label
    for i in range(3, len(s) + 1):
        col_1_based = (col_1_based - z_to_a) * 26 + (ord(s[i]) - 65)
    
    return col_1_based

# Check function with provided data points
def check_function():
    assert col_number('ZZ') == 88, "Test case 1 failed"
    assert col_number('ZZA') == 88, "Test case 2 failed"
    assert col_number('AAZ') == 703, "Test case 3 failed"
    assert col_number('AZ') == 52, "Test case 4 failed"
    assert col_number('ABCDEFGH') == 61 * 7 * 8 + ord('B') - 65 = 1988
    print("All test cases passed!")

check_function()
