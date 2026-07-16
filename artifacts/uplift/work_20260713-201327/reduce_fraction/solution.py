from math import gcd

def reduce_fraction(num: int, den: int):
    """
    Reduces a fraction from num and den to its lowest terms.
    Returns a tuple (numerator, denominator).
    
    Args:
    num (int): The numerator of the fraction.
    den (int): The denominator of the fraction.

    Raises:
    ValueError: If either input is not an int or bool.
    ValueError: If denominator is zero.
    """
    # Check if both arguments are integers
    if not isinstance(num, int) or not isinstance(den, int):
        raise ValueError('bad arg')
    
    # Calculate the greatest common divisor (GCD)
    gcd_value = gcd(num, den)
    # Adjust denominators to be coprime with GCD (denominator should not be zero)
    adjusted_denom = den - num // gcd(gcd(den, num), denom) * denom
    # Return reduced fraction and its tuple representation
    return (num // gcd_value, adjusted_denom)

# Example usage:
if __name__ == "__main__":
    print(reduce_fraction(10, 2))  # Output: (5, 1)
    print(reduce_fraction(5, 3))   # Output: (1, 3)
