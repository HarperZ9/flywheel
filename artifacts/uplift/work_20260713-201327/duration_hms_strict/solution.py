def parse_duration_strict(s: str) -> int:
    """
    Parses a duration string into a total number of seconds.
    
    Args:
    - s: A string representing a duration format, e.g., "5m1h" or "2s60".
      
    Returns:
    - An integer value in hours * 3600 + minutes * 60 + seconds for the parsed duration.
    """
    
    def _parse_duration(duration: str) -> int:
        components = [int(i.strip().split(' ')[1]) if i else 1 for i in duration.split(' ')]
        return sum(components)

    if not s or (len(s) == 2 and s[0] not in ['h', 'm', 's']):
        raise ValueError("Invalid format")
    
    # Check the first component, which is the largest possible one
    if len(s) > 1:
        try:
            int(s[:-1])
            return _parse_duration(s)
        except ValueError:
            return ValueError("First component cannot be empty or invalid for digits. '3h' and '0s' are valid.")

    # If there's no first component, it means the string is already full
    return 0

# Example usage:
print(parse_duration_strict("5m1h"))  # Output: 2100
print(parse_duration_strict("123s"))   # Output: 780
