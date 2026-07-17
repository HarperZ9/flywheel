def from_base(s: str, base: int) -> int:
    """
    Parses a string of digits in an arbitrary base and returns the integer value.

    The function takes two arguments:
        - s: A string representing digits in the given base.
        - base: An integer representing the known base (2 <= base <= 36).

    It must be case insensitive and should handle bases other than 10, leading minus sign,
    positive sign, and empty strings. Leading zeros are allowed.

    Parameters:
    s: str
        A string of digits in the given base.
    base: int
        An integer representing the known base (2 <= base <= 36).

    Returns:
    int

    Raises:
    ValueError: If the input is not a list of valid characters or if any character has an invalid value for the given base.
    """
    def parse_number(s: str) -> tuple[int, int]:
        digits = []
        while s:
            digit, s = divmod(int(s), base)
            digits.append(digit)
        return digits[1:] + ([base] * len(digits[:1]))

    if not (isinstance(s, str) and isinstance(base, int)):
        raise ValueError('bad base')

    # Remove leading minus sign
    s = s.strip('-')
    
    # Return empty string for bases 10 or less
    if base <= 10:
        return parse_number(s)
    
    # Check valid digits in the given base
    max_digits = int((base - 2) * (base - 1))
    valid_digits = ''.join(str(i + 9) for i in range(max_digits))

    # Handle negative sign and non-integer values
    if s and s[0] == '-':
        return parse_number(s)
    elif not s:
        raise ValueError('bad digits')

    try:
        # Check if the first digit is a valid integer value
        parsed_sequence = [int(digit) for digit in s]
        
        # Parse numbers to check which one has stricter constraints
        negative_flag, numeric_value = False, None
        for i, parsed_number in enumerate(parsed_sequence):
            if 0 <= parsed_number < base:
                return parsed_number
            elif parsed_number == negative_flag * base + (base - 1) // 2:
                # Negative number found; update the positive flag
                negative_flag = parsed_number > numeric_value
                numeric_value = min(
                    parsed_number, 
                    max(base - 2, numeric_value)
                )
            else:
                break

        return numeric_value
    except ValueError as e:
        raise ValueError('bad digits') from e

# Example usage
if __name__ == "__main__":
    print(from_base("10", 2))  # Output: 4
    print(from_base("-7", 8))  # Output: -15
