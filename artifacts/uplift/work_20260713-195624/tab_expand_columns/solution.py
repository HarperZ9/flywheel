def expand_tabs(s, stop):
    """
    Expands tab characters into spaces using tab stops every 'stop' columns.
    
    Parameters:
    s (str): The input string containing special tabs and newlines.
    stop (int): The number of columns after which to split the string on a tab.
                 It must be at least 1, but can be any value greater than 1.

    Returns:
    str: A string with the specified splitting pattern.
    """
    if not isinstance(stop, int) or not all(isinstance(c, str) and c in 'tab' for c in s):
        raise ValueError('bad stop')

    # Calculate the number of lines (columns) to be returned
    return '\n'.join(s[i * stop:(i + 1) * stop] if i * stop < len(s) else ' ' for i in range(int(len(s) / (stop * len(s.split('\n'))))))


# Check function with provided data points
print(expand_tabs("Hello\tWorld", 4))  # Expected output: "  Hello \t    World"
print(expand_tabs("\tTab\nnewline\n\r", 2))  # Expected output: "\n tab new line\r"
