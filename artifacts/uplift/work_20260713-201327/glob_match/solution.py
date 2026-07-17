import re

def glob_match(pattern: str, name: str) -> bool:
    """
    Check if the given name matches the specified glob pattern.

    Parameters:
    pattern (str): A glob pattern that includes wildcards like '/*', '?'.
    name (str): The name to match against the pattern.

    Returns:
    bool: True if the name matches the pattern, False otherwise.
    """
    # Convert patterns to a regular expression for easier matching
    regex_pattern = re.compile(r'/' + pattern)
    
    # Check if the entire name matches the pattern with no part of it being a prefix or substring
    return not regex_pattern.search(name)

# Example usage:
# glob_match("/*", "example/*")
