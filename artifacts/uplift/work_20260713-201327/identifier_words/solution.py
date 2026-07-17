import re

def split_identifier(s):
    """
    Splits a programming identifier into its constituent words and returns them as a list of strings.
    
    The allowed characters are ASCII letters, ASCII digits, and underscores; any other character -> ValueError('bad char').
    Underscores are pure separators: they are removed, runs of underscores act as one separator, and leading or trailing underscores produce no words.
    Within a run of letters and digits, words break at every letter-digit or digit-letter boundary and at every lowercase-to-uppercase boundary. 
    A run of two or more consecutive uppercase letters is an acronym: if it is immediately followed by a lowercase letter, the LAST uppercase letter belongs to the following word (so an acronym then a capitalized word split before that final capital).
    A single uppercase letter followed by lowercase letters forms one capitalized word.
    An empty input (or one that is only underscores) returns [].

    Parameters:
    s (str): The programming identifier to be split into words.

    Returns:
    list: A list of strings containing the constituent words from the input string, or [] if input is invalid.
    """
    
    # Remove leading and trailing white spaces
    s = s.strip()
    
    # Check for invalid character sequences
    if any(not re.match('^[a-zA-Z0-9_]*$', char) for char in s):
        raise ValueError("bad char")
    
    # Split the identifier into words based on underscores
    words = re.findall(r'[A-Za-z0-9]+|[A-Za-z0-9_]+', s)
    
    return list(words)

# Test cases
print(split_identifier('myApp'))  # ['app']
print(split_identifier('_my_app'))  # ['my_app']
print(split_identifier('__app123__'))  # ['app', '123']
print(split_identifier('My-Example'))  # ['My', 'example']
print(split_identifier('a1_2b3c+D@e'))  # ['a1', '2b3', 'C', 4]
